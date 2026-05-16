#!/bin/bash
set -euo pipefail
export PATH="/usr/local/cargo/bin:${PATH:-}"
cd /app
mkdir -p src output

cat > Cargo.toml <<'EOF'
[package]
name = "spanrecon"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1.0.210", features = ["derive"] }
serde_json = "1.0.128"
EOF

cat > src/main.rs <<'RS'
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};
use std::fs;
use std::path::{Path, PathBuf};

const DATA: &str = "/app/data";
const OUT: &str = "/app/output";

fn shard_paths(base: &Path) -> Vec<PathBuf> {
    let dir = base.join("shards");
    let Ok(rd) = fs::read_dir(&dir) else {
        return Vec::new();
    };
    let mut names: Vec<String> = rd
        .filter_map(|e| e.ok())
        .map(|e| e.file_name().to_string_lossy().into_owned())
        .filter(|n| n.ends_with(".json"))
        .collect();
    names.sort();
    names.into_iter().map(|n| dir.join(n)).collect()
}

fn iter_rows(base: &Path) -> Vec<Value> {
    let mut out = Vec::new();
    for path in shard_paths(base) {
        let Ok(text) = fs::read_to_string(&path) else {
            continue;
        };
        let Ok(val) = serde_json::from_str::<Value>(&text) else {
            continue;
        };
        let Some(arr) = val.as_array() else {
            continue;
        };
        for v in arr {
            out.push(v.clone());
        }
    }
    out
}

fn well_formed(v: &Value) -> Option<(String, String, Option<String>, i64, i64)> {
    let obj = v.as_object()?;
    let tid = obj
        .get("trace_id")
        .and_then(|x| x.as_str())
        .filter(|s| !s.is_empty())?
        .to_string();
    let sid = obj
        .get("span_id")
        .and_then(|x| x.as_str())
        .filter(|s| !s.is_empty())?
        .to_string();
    let parent = match obj.get("parent_id")? {
        Value::Null => None,
        Value::String(s) => Some(s.clone()),
        _ => return None,
    };
    let sm = obj.get("start_ms").and_then(|x| x.as_i64())?;
    let em = obj.get("end_ms").and_then(|x| x.as_i64())?;
    Some((tid, sid, parent, sm, em))
}

fn write_json(path: &Path, v: &Value) {
    let mut s = serde_json::to_string_pretty(v).expect("serialize");
    s.push('\n');
    fs::write(path, s).expect("write");
}

fn main() {
    let base = Path::new(DATA);
    let rows = iter_rows(base);

    let mut g: i64 = 0;
    let mut claimed: BTreeMap<String, BTreeMap<String, i64>> = BTreeMap::new();
    let mut dup_events: Vec<(String, String, i64, i64)> = Vec::new();
    let mut invalid_time_events: i64 = 0;
    let mut ingested: i64 = 0;
    let mut canon: Vec<(String, String, Option<String>)> = Vec::new();

    for v in &rows {
        let Some((tid, sid, parent, sm, em)) = well_formed(v) else {
            continue;
        };
        if em < sm {
            invalid_time_events += 1;
        }
        let entry = claimed.entry(tid.clone()).or_default();
        if let Some(&first_idx) = entry.get(&sid) {
            dup_events.push((tid.clone(), sid.clone(), first_idx, g));
            g += 1;
            ingested += 1;
            continue;
        }
        entry.insert(sid.clone(), g);
        canon.push((tid, sid, parent));
        g += 1;
        ingested += 1;
    }

    let mut traces_ids: BTreeSet<String> = BTreeSet::new();
    for v in &rows {
        if let Some((tid, _, _, _, _)) = well_formed(v) {
            traces_ids.insert(tid);
        }
    }

    let mut by_trace: BTreeMap<String, Vec<(String, Option<String>)>> = BTreeMap::new();
    for (tid, sid, parent) in &canon {
        by_trace
            .entry(tid.clone())
            .or_default()
            .push((sid.clone(), parent.clone()));
    }

    let mut self_parent: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut orphan: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut roots: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut children: BTreeMap<String, BTreeMap<String, Vec<String>>> = BTreeMap::new();

    let mut claimed_ids: HashMap<String, BTreeSet<String>> = HashMap::new();
    for (tid, inner) in &claimed {
        claimed_ids.insert(
            tid.clone(),
            inner.keys().cloned().collect(),
        );
    }

    for (tid, sid, parent) in &canon {
        match parent {
            None => {
                roots.entry(tid.clone()).or_default().insert(sid.clone());
            }
            Some(p) if p == sid => {
                self_parent
                    .entry(tid.clone())
                    .or_default()
                    .insert(sid.clone());
            }
            Some(p) => {
                let ids = claimed_ids.get(tid).cloned().unwrap_or_default();
                if !ids.contains(p) {
                    orphan.entry(tid.clone()).or_default().insert(sid.clone());
                } else {
                    children
                        .entry(tid.clone())
                        .or_default()
                        .entry(p.clone())
                        .or_default()
                        .push(sid.clone());
                }
            }
        }
    }

    for (_tid, pmap) in children.iter_mut() {
        for (_p, chs) in pmap.iter_mut() {
            chs.sort();
        }
    }

    let mut dup_in_trace: BTreeMap<String, i64> = BTreeMap::new();
    for (tid, _, _, _) in &dup_events {
        *dup_in_trace.entry(tid.clone()).or_insert(0) += 1;
    }

    let mut invalid_in_trace: BTreeMap<String, i64> = BTreeMap::new();
    for v in &rows {
        if let Some((tid, _, _, sm, em)) = well_formed(v) {
            if em < sm {
                *invalid_in_trace.entry(tid).or_insert(0) += 1;
            }
        }
    }

    let max_depth_for = |tid: &str| -> i64 {
        let mut depths: BTreeMap<String, i64> = BTreeMap::new();
        let mut dq: VecDeque<String> = VecDeque::new();
        let rset = roots.get(tid).cloned().unwrap_or_default();
        let sp = self_parent.get(tid).cloned().unwrap_or_default();
        let orp = orphan.get(tid).cloned().unwrap_or_default();
        for r in rset.iter() {
            if sp.contains(r) || orp.contains(r) {
                continue;
            }
            depths.insert(r.clone(), 0);
            dq.push_back(r.clone());
        }
        while let Some(p) = dq.pop_front() {
            let dp = *depths.get(&p).unwrap_or(&0);
            if let Some(chmap) = children.get(tid) {
                if let Some(chs) = chmap.get(&p) {
                    for ch in chs {
                        if sp.contains(ch) || orp.contains(ch) {
                            continue;
                        }
                        depths.insert(ch.clone(), dp + 1);
                        dq.push_back(ch.clone());
                    }
                }
            }
        }
        depths.values().copied().max().unwrap_or(0)
    };

    let mut traces_arr: Vec<Value> = Vec::new();
    for tid in by_trace.keys() {
        let canon_count = by_trace.get(tid).map(|v| v.len()).unwrap_or(0) as i64;
        let dup_ct = *dup_in_trace.get(tid).unwrap_or(&0);
        let inv_ct = *invalid_in_trace.get(tid).unwrap_or(&0);
        let md = max_depth_for(tid);
        let ors: Vec<Value> = orphan
            .get(tid)
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .map(Value::String)
            .collect();
        let rs: Vec<Value> = roots
            .get(tid)
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .map(Value::String)
            .collect();
        let sps: Vec<Value> = self_parent
            .get(tid)
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .map(Value::String)
            .collect();
        let mut obj = Map::new();
        obj.insert("canonical_span_count".into(), json!(canon_count));
        obj.insert("duplicate_events_in_trace".into(), json!(dup_ct));
        obj.insert("invalid_time_events_in_trace".into(), json!(inv_ct));
        obj.insert("max_depth".into(), json!(md));
        obj.insert(
            "orphan_span_ids".into(),
            Value::Array(ors),
        );
        obj.insert("roots".into(), Value::Array(rs));
        obj.insert(
            "self_parent_span_ids".into(),
            Value::Array(sps),
        );
        obj.insert("trace_id".into(), Value::String(tid.clone()));
        traces_arr.push(Value::Object(obj));
    }

    dup_events.sort_by(|a, b| {
        (a.0.as_str(), a.1.as_str(), a.3, a.2).cmp(&(b.0.as_str(), b.1.as_str(), b.3, b.2))
    });

    let mut dup_json: Vec<Value> = Vec::new();
    for (tid, sid, first_idx, later_idx) in &dup_events {
        let mut m = Map::new();
        m.insert("first_index".into(), json!(first_idx));
        m.insert("later_index".into(), json!(later_idx));
        m.insert("span_id".into(), Value::String(sid.clone()));
        m.insert("trace_id".into(), Value::String(tid.clone()));
        dup_json.push(Value::Object(m));
    }

    let orphan_rows: i64 = orphan.values().map(|s| s.len() as i64).sum();
    let self_rows: i64 = self_parent.values().map(|s| s.len() as i64).sum();

    let mut summary = Map::new();
    summary.insert("duplicate_events".into(), json!(dup_events.len() as i64));
    summary.insert("ingested_well_formed_rows".into(), json!(ingested));
    summary.insert("invalid_time_events".into(), json!(invalid_time_events));
    summary.insert("orphan_canonical_rows".into(), json!(orphan_rows));
    summary.insert(
        "self_parent_canonical_rows".into(),
        json!(self_rows),
    );
    summary.insert("trace_count".into(), json!(traces_ids.len() as i64));

    fs::create_dir_all(OUT).expect("mkdir");
    write_json(
        &Path::new(OUT).join("summary.json"),
        &Value::Object(summary),
    );
    write_json(
        &Path::new(OUT).join("duplicates.json"),
        &json!({ "events": dup_json }),
    );
    write_json(
        &Path::new(OUT).join("traces.json"),
        &json!({ "traces": traces_arr }),
    );
}
RS

cargo build --release
find /app/output -mindepth 1 -maxdepth 1 -delete 2>/dev/null || true
mkdir -p /app/output
./target/release/spanrecon
