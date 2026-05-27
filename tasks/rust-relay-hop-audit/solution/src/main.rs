use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

fn env_or(key: &str, default: &str) -> String {
    env::var(key).unwrap_or_else(|_| default.to_string())
}

fn read_json(path: &Path) -> Value {
    let raw = fs::read_to_string(path).expect("read");
    serde_json::from_str(&raw).expect("parse")
}

fn write_json(path: &Path, v: &Value) {
    fs::write(path, serde_json::to_string_pretty(v).unwrap() + "\n").expect("write");
}

fn sorted_glob(dir: &Path, suffix: &str) -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Ok(rd) = fs::read_dir(dir) {
        for ent in rd.flatten() {
            let p = ent.path();
            if p.extension().and_then(|s| s.to_str()) == Some(&suffix[1..]) {
                out.push(p);
            }
        }
    }
    out.sort();
    out
}

fn cap_core(h: &str, base: &HashMap<String, i64>, delta: &HashMap<String, i64>, halted: &HashMap<String, bool>) -> i64 {
    if halted.get(h).copied().unwrap_or(false) {
        return 0;
    }
    let v = base.get(h).copied().unwrap_or(0) + delta.get(h).copied().unwrap_or(0);
    if v < 1 { 1 } else { v }
}

fn main() {
    let data_dir = PathBuf::from(env_or("RRH_DATA_DIR", "/app/relayhop"));
    let audit_dir = PathBuf::from(env_or("RRH_AUDIT_DIR", "/app/audit"));
    fs::create_dir_all(&audit_dir).expect("mkdir audit");

    let pol = read_json(&data_dir.join("policy.json"));
    let inc_file = read_json(&data_dir.join("incidents.json"));
    let carry_max = pol["carry_max"].as_i64().unwrap();
    let epochs: Vec<i64> = pol["epochs"].as_array().unwrap().iter().map(|x| x.as_i64().unwrap()).collect();
    let hops_order: Vec<String> = pol["hops_order"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect();

    let mut base: HashMap<String, i64> = HashMap::new();
    for p in sorted_glob(&data_dir.join("hops"), ".json") {
        let hf = read_json(&p);
        base.insert(hf["hop_id"].as_str().unwrap().to_string(), hf["base_cap"].as_i64().unwrap());
    }

    #[derive(Clone)]
    struct Flow { flow_id: String, epoch: i64, hop_id: String, bytes: i64 }
    let mut flows = Vec::new();
    for p in sorted_glob(&data_dir.join("flows"), ".json") {
        let ff = read_json(&p);
        flows.push(Flow {
            flow_id: ff["flow_id"].as_str().unwrap().to_string(),
            epoch: ff["epoch"].as_i64().unwrap(),
            hop_id: ff["hop_id"].as_str().unwrap().to_string(),
            bytes: ff["bytes"].as_i64().unwrap(),
        });
    }

    let epoch_set: BTreeSet<i64> = epochs.iter().copied().collect();
    for f in &flows {
        if !epoch_set.contains(&f.epoch) || !base.contains_key(&f.hop_id) {
            std::process::exit(1);
        }
    }
    let hop_set: BTreeSet<_> = hops_order.iter().cloned().collect();
    if hop_set.len() != hops_order.len() || hop_set.len() != base.len() {
        std::process::exit(1);
    }
    for h in base.keys() {
        if !hop_set.contains(h) { std::process::exit(1); }
    }

    let mut delta: HashMap<String, i64> = hops_order.iter().map(|h| (h.clone(), 0)).collect();
    let mut carry: HashMap<String, i64> = hops_order.iter().map(|h| (h.clone(), 0)).collect();
    let mut halted: HashMap<String, bool> = hops_order.iter().map(|h| (h.clone(), false)).collect();

    let mut admissions: Vec<Value> = Vec::new();
    let mut denials: Vec<Value> = Vec::new();
    let mut ledgers: Vec<Value> = Vec::new();

    for &e in &epochs {
        for inc in inc_file["incidents"].as_array().unwrap() {
            if inc["epoch"].as_i64().unwrap() != e { continue; }
            let kind = inc["kind"].as_str().unwrap();
            if kind == "noop" { continue; }
            let h = inc["hop_id"].as_str().unwrap();
            match kind {
                "cap_add" => { *delta.get_mut(h).unwrap() += inc["delta"].as_i64().unwrap(); }
                "halt_hop" => { halted.insert(h.to_string(), true); carry.insert(h.to_string(), 0); }
                "resume_hop" => { halted.insert(h.to_string(), false); carry.insert(h.to_string(), 0); }
                _ => std::process::exit(1),
            }
        }

        let mut cin: HashMap<String, i64> = HashMap::new();
        let mut used: HashMap<String, i64> = HashMap::new();
        for h in &hops_order {
            cin.insert(h.clone(), *carry.get(h).unwrap());
            used.insert(h.clone(), 0);
        }

        let mut epoch_flows: Vec<&Flow> = flows.iter().filter(|f| f.epoch == e).collect();
        epoch_flows.sort_by(|a, b| a.hop_id.cmp(&b.hop_id).then(a.flow_id.cmp(&b.flow_id)));

        for f in epoch_flows {
            let h = &f.hop_id;
            let b = f.bytes;
            let mut avail = cap_core(h, &base, &delta, &halted) + cin[h] - used[h];
            if avail < 0 { avail = 0; }
            if b <= avail {
                *used.get_mut(h).unwrap() += b;
                admissions.push(json!({"bytes": b, "epoch": e, "flow_id": f.flow_id, "hop_id": h}));
            } else {
                denials.push(json!({"available": avail, "epoch": e, "flow_id": f.flow_id, "hop_id": h, "requested": b}));
            }
        }

        for h in &hops_order {
            let cc = cap_core(h, &base, &delta, &halted);
            let rem = cc + cin[h] - used[h];
            let mut cout = carry_max.min(0.max(rem));
            if halted[h] { cout = 0; }
            ledgers.push(json!({"cap_core": cc, "carry_in": cin[h], "carry_out": cout, "epoch": e, "hop_id": h, "used": used[h]}));
            carry.insert(h.clone(), cout);
        }
    }

    admissions.sort_by(|a, b| {
        let (ae, ah, af) = (a["epoch"].as_i64().unwrap(), a["hop_id"].as_str().unwrap(), a["flow_id"].as_str().unwrap());
        let (be, bh, bf) = (b["epoch"].as_i64().unwrap(), b["hop_id"].as_str().unwrap(), b["flow_id"].as_str().unwrap());
        ae.cmp(&be).then(ah.cmp(bh)).then(af.cmp(bf))
    });
    denials.sort_by(|a, b| {
        let (ae, ah, af) = (a["epoch"].as_i64().unwrap(), a["hop_id"].as_str().unwrap(), a["flow_id"].as_str().unwrap());
        let (be, bh, bf) = (b["epoch"].as_i64().unwrap(), b["hop_id"].as_str().unwrap(), b["flow_id"].as_str().unwrap());
        ae.cmp(&be).then(ah.cmp(bh)).then(af.cmp(bf))
    });
    ledgers.sort_by(|a, b| {
        a["epoch"].as_i64().unwrap().cmp(&b["epoch"].as_i64().unwrap())
            .then(a["hop_id"].as_str().unwrap().cmp(b["hop_id"].as_str().unwrap()))
    });

    let applied: Vec<Value> = inc_file["incidents"].as_array().unwrap().iter().map(|i| i["kind"].clone()).collect();
    let mut max_ep = 0i64;
    for inc in inc_file["incidents"].as_array().unwrap() {
        max_ep = max_ep.max(inc["epoch"].as_i64().unwrap());
    }
    for a in &admissions { max_ep = max_ep.max(a["epoch"].as_i64().unwrap()); }
    for d in &denials { max_ep = max_ep.max(d["epoch"].as_i64().unwrap()); }

    let tot_adm = admissions.len() as i64;
    let tot_adm_bytes: i64 = admissions.iter().map(|a| a["bytes"].as_i64().unwrap()).sum();
    let tot_den = denials.len() as i64;
    let tot_den_bytes: i64 = denials.iter().map(|d| d["requested"].as_i64().unwrap()).sum();

    write_json(&audit_dir.join("admissions.json"), &json!({"admissions": admissions}));
    write_json(&audit_dir.join("denials.json"), &json!({"denials": denials}));
    write_json(&audit_dir.join("carry_ledgers.json"), &json!({"rows": ledgers}));
    write_json(&audit_dir.join("summary.json"), &json!({
        "incidents_applied": applied,
        "max_epoch": max_ep,
        "total_admissions": tot_adm,
        "total_admitted_bytes": tot_adm_bytes,
        "total_denials": tot_den,
        "total_denied_bytes": tot_den_bytes,
    }));
}
