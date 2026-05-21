use serde_json::{Map, Number, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

fn read_json(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("read {}: {e}", path.display()))?;
    serde_json::from_str(&text).map_err(|e| format!("parse {}: {e}", path.display()))
}

fn sort_value_keys(v: &Value) -> Value {
    match v {
        Value::Object(m) => {
            let mut keys: Vec<String> = m.keys().cloned().collect();
            keys.sort();
            let mut out = Map::new();
            for k in keys {
                if let Some(c) = m.get(&k) {
                    out.insert(k, sort_value_keys(c));
                }
            }
            Value::Object(out)
        }
        Value::Array(a) => Value::Array(a.iter().map(sort_value_keys).collect()),
        _ => v.clone(),
    }
}

fn write_json(path: &Path, v: &Value) -> Result<(), String> {
    let sorted = sort_value_keys(v);
    let mut s =
        serde_json::to_string_pretty(&sorted).map_err(|e| format!("serialize {}: {e}", path.display()))?;
    s.push('\n');
    fs::write(path, s).map_err(|e| format!("write {}: {e}", path.display()))
}

fn as_i64(v: &Value, ctx: &str) -> Result<i64, String> {
    v.as_i64()
        .or_else(|| v.as_u64().and_then(|u| i64::try_from(u).ok()))
        .ok_or_else(|| format!("{ctx}: expected integer"))
}

fn validate_hex64(s: &str) -> Result<(), String> {
    if s.len() != 64 {
        return Err("master_seed_hex must be 64 chars".into());
    }
    if !s.chars().all(|c| matches!(c, '0'..='9' | 'a'..='f')) {
        return Err("master_seed_hex must be lowercase hex".into());
    }
    Ok(())
}

fn hash_u64(mix: &str) -> u64 {
    let digest = Sha256::digest(mix.as_bytes());
    u64::from_be_bytes(digest[..8].try_into().unwrap())
}

fn score_arm(a: i64, b: i64, seed: &str, round_id: &str, phase: &str, step: i64, arm_id: &str) -> i64 {
    let mix = format!("{seed}:{round_id}:{phase}:{step}:{arm_id}");
    let h = hash_u64(&mix);
    let sum = a + b;
    let denom = if sum < 1 { 1 } else { sum };
    let mean_scaled = (a * 1_000_000) / denom;
    let tie = (h % 10_000) as i64;
    mean_scaled * 10_000 + tie
}

fn load_dir_json(dir: &Path) -> Result<Vec<(PathBuf, Value)>, String> {
    if !dir.is_dir() {
        return Ok(Vec::new());
    }
    let mut paths: Vec<PathBuf> = fs::read_dir(dir)
        .map_err(|e| format!("read_dir {}: {e}", dir.display()))?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|x| x.to_str()) == Some("json"))
        .collect();
    paths.sort();
    let mut out = Vec::new();
    for p in paths {
        out.push((p.clone(), read_json(&p)?));
    }
    Ok(out)
}

#[derive(Clone, Debug)]
struct Arm {
    arm_id: String,
    pull_cost: i64,
    start_alpha: i64,
    start_beta: i64,
    alpha: i64,
    beta: i64,
    selections: i64,
    successes: i64,
    voids: i64,
}

#[derive(Clone, Debug, Default)]
struct RoundRec {
    round_id: String,
    phase_token: String,
    candidates: Vec<String>,
    pulls: Vec<Value>,
}

fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        return Err("expected two argv paths: <lab_dir> <out_dir>".into());
    }
    let lab: PathBuf = args[1].clone().into();
    let out: PathBuf = args[2].clone().into();
    fs::create_dir_all(&out).map_err(|e| format!("mkdir out: {e}"))?;

    let policy = read_json(&lab.join("policy.json"))?;
    let pool = read_json(&lab.join("pool_state.json"))?;
    let incidents_root = read_json(&lab.join("incident_log.json"))?;

    let audit_schema = policy
        .get("audit_schema_version")
        .and_then(Value::as_str)
        .ok_or("policy.audit_schema_version missing")?;
    if audit_schema != "pqb-1" {
        return Err("audit_schema_version must be pqb-1".into());
    }
    let seed = policy
        .get("master_seed_hex")
        .and_then(Value::as_str)
        .ok_or("policy.master_seed_hex missing")?;
    validate_hex64(seed)?;

    let current_day = as_i64(pool.get("current_day").ok_or("pool.current_day missing")?, "pool.current_day")?;
    let audit_version = pool
        .get("audit_version")
        .and_then(Value::as_str)
        .ok_or("pool.audit_version missing")?
        .to_string();

    let global_alpha = as_i64(policy.get("global_alpha").ok_or("policy.global_alpha missing")?, "policy.global_alpha")?;
    let global_beta = as_i64(policy.get("global_beta").ok_or("policy.global_beta missing")?, "policy.global_beta")?;
    let shrink_num = as_i64(policy.get("shrink_num").ok_or("policy.shrink_num missing")?, "policy.shrink_num")?;
    let shrink_den = as_i64(policy.get("shrink_den").ok_or("policy.shrink_den missing")?, "policy.shrink_den")?;
    if shrink_den <= 0 {
        return Err("shrink_den must be positive".into());
    }
    if shrink_num < 0 || shrink_num > shrink_den {
        return Err("shrink_num out of range".into());
    }
    let quorum_distinct = as_i64(
        policy
            .get("quorum_distinct")
            .ok_or("policy.quorum_distinct missing")?,
        "policy.quorum_distinct",
    )?;
    if quorum_distinct <= 0 {
        return Err("quorum_distinct must be positive".into());
    }
    let budget_tokens = as_i64(
        policy
            .get("budget_tokens")
            .ok_or("policy.budget_tokens missing")?,
        "policy.budget_tokens",
    )?;
    if budget_tokens < 0 {
        return Err("budget_tokens must be non-negative".into());
    }

    let supported_kinds = policy
        .get("supported_incident_kinds")
        .and_then(Value::as_array)
        .ok_or("policy.supported_incident_kinds missing")?
        .iter()
        .map(|v| v.as_str().ok_or("supported_incident_kinds must be strings"))
        .collect::<Result<Vec<_>, _>>()?;

    let mut rater_weights: BTreeMap<String, i64> = BTreeMap::new();
    let rw_obj = policy
        .get("rater_weights")
        .and_then(Value::as_object)
        .ok_or("policy.rater_weights missing")?;
    for (k, v) in rw_obj {
        let w = as_i64(v, &format!("rater_weights[{k}]"))?;
        if w <= 0 {
            return Err(format!("rater_weights[{k}] must be positive"));
        }
        rater_weights.insert(k.clone(), w);
    }

    let mut arms_raw: Vec<(String, i64, i64, i64)> = Vec::new();
    for (p, row) in load_dir_json(&lab.join("arms"))? {
        let arm_id = row
            .get("arm_id")
            .and_then(Value::as_str)
            .ok_or_else(|| format!("{}.arm_id missing", p.display()))?
            .to_string();
        let pa = as_i64(row.get("prior_alpha").ok_or("arm.prior_alpha missing")?, "prior_alpha")?;
        let pb = as_i64(row.get("prior_beta").ok_or("arm.prior_beta missing")?, "prior_beta")?;
        let pc = as_i64(row.get("pull_cost").ok_or("arm.pull_cost missing")?, "pull_cost")?;
        if pa <= 0 || pb <= 0 || pc <= 0 {
            return Err(format!("{}. prior_alpha/prior_beta/pull_cost must be positive", p.display()));
        }
        arms_raw.push((arm_id, pa, pb, pc));
    }
    arms_raw.sort_by(|a, b| a.0.cmp(&b.0));
    let mut seen: BTreeSet<String> = BTreeSet::new();
    for (id, _, _, _) in &arms_raw {
        if !seen.insert(id.clone()) {
            return Err(format!("duplicate arm_id {id}"));
        }
    }

    let incidents = incidents_root
        .get("incidents")
        .and_then(Value::as_array)
        .ok_or("incident_log.incidents missing")?
        .clone();

    let mut pri_a: BTreeMap<String, i64> = BTreeMap::new();
    let mut pri_b: BTreeMap<String, i64> = BTreeMap::new();
    let mut pull_cost: BTreeMap<String, i64> = BTreeMap::new();
    for (id, pa, pb, pc) in arms_raw {
        pri_a.insert(id.clone(), pa);
        pri_b.insert(id.clone(), pb);
        pull_cost.insert(id, pc);
    }

    let mut prior_bumps: Vec<Value> = Vec::new();
    let mut freezes: Vec<Value> = Vec::new();
    let mut reliefs: Vec<Value> = Vec::new();

    let mut ignored = 0i64;
    let mut active = 0i64;

    for inc in &incidents {
        let kind = inc.get("kind").and_then(Value::as_str).unwrap_or("");
        let accepted = inc.get("accepted").and_then(Value::as_bool) == Some(true);
        let day = inc.get("day").and_then(Value::as_i64).unwrap_or(-1);
        let supported = supported_kinds.iter().any(|k| *k == kind);
        let active_row = accepted && day <= current_day && supported;
        if !active_row {
            ignored += 1;
            continue;
        }
        match kind {
            "prior_bump" => {
                if inc.get("arm_id").and_then(Value::as_str).is_none()
                    || inc.get("alpha_delta").and_then(Value::as_i64).is_none()
                {
                    ignored += 1;
                    continue;
                }
                let d = as_i64(inc.get("alpha_delta").unwrap(), "alpha_delta")?;
                if d <= 0 {
                    ignored += 1;
                    continue;
                }
                prior_bumps.push(inc.clone());
            }
            "arm_freeze" => {
                let aid = match inc.get("arm_id").and_then(Value::as_str) {
                    Some(s) => s,
                    None => {
                        ignored += 1;
                        continue;
                    }
                };
                if inc.get("thaw_day").and_then(Value::as_i64).is_none() {
                    ignored += 1;
                    continue;
                }
                if !pri_a.contains_key(aid) {
                    ignored += 1;
                    continue;
                }
                freezes.push(inc.clone());
            }
            "quorum_relief" => {
                if inc.get("round_id").and_then(Value::as_str).is_none()
                    || inc.get("relief").and_then(Value::as_i64).is_none()
                {
                    ignored += 1;
                    continue;
                }
                let r = as_i64(inc.get("relief").unwrap(), "relief")?;
                if r < 0 {
                    ignored += 1;
                    continue;
                }
                reliefs.push(inc.clone());
            }
            _ => {
                ignored += 1;
                continue;
            }
        }
        active += 1;
    }

    prior_bumps.sort_by(|a, b| {
        let da = a.get("day").and_then(Value::as_i64).unwrap_or(0);
        let db = b.get("day").and_then(Value::as_i64).unwrap_or(0);
        da.cmp(&db).then_with(|| {
            let ea = a.get("event_id").and_then(Value::as_str).unwrap_or("");
            let eb = b.get("event_id").and_then(Value::as_str).unwrap_or("");
            ea.cmp(eb)
        })
    });

    for bump in &prior_bumps {
        let aid = bump.get("arm_id").and_then(Value::as_str).unwrap();
        let d = as_i64(bump.get("alpha_delta").unwrap(), "alpha_delta")?;
        let e = pri_a.get(aid).ok_or_else(|| format!("prior_bump unknown arm {aid}"))?;
        pri_a.insert(aid.to_string(), e + d);
    }

    let mut arms: BTreeMap<String, Arm> = BTreeMap::new();
    for id in pri_a.keys() {
        let pa = *pri_a.get(id).unwrap();
        let pb = *pri_b.get(id).unwrap();
        let pc = *pull_cost.get(id).unwrap();
        let mut a = (pa * (shrink_den - shrink_num) + global_alpha * shrink_num) / shrink_den;
        let mut b = (pb * (shrink_den - shrink_num) + global_beta * shrink_num) / shrink_den;
        if a < 1 {
            a = 1;
        }
        if b < 1 {
            b = 1;
        }
        arms.insert(
            id.clone(),
            Arm {
                arm_id: id.clone(),
                pull_cost: pc,
                start_alpha: a,
                start_beta: b,
                alpha: a,
                beta: b,
                selections: 0,
                successes: 0,
                voids: 0,
            },
        );
    }

    let mut rounds: Vec<RoundRec> = Vec::new();
    for (p, row) in load_dir_json(&lab.join("rounds"))? {
        let round_id = row
            .get("round_id")
            .and_then(Value::as_str)
            .ok_or_else(|| format!("{}.round_id missing", p.display()))?
            .to_string();
        let phase_token = row
            .get("phase_token")
            .and_then(Value::as_str)
            .ok_or_else(|| format!("{}.phase_token missing", p.display()))?
            .to_string();
        let candidates = row
            .get("candidates")
            .and_then(Value::as_array)
            .ok_or_else(|| format!("{}.candidates missing", p.display()))?
            .iter()
            .map(|v| v.as_str().map(|s| s.to_string()).ok_or("candidate must be string"))
            .collect::<Result<Vec<_>, _>>()?;
        let pulls = row
            .get("pulls")
            .and_then(Value::as_array)
            .ok_or_else(|| format!("{}.pulls missing", p.display()))?
            .clone();
        for c in &candidates {
            if !arms.contains_key(c) {
                return Err(format!("unknown candidate arm {c} in {}", p.display()));
            }
        }
        rounds.push(RoundRec {
            round_id,
            phase_token,
            candidates,
            pulls,
        });
    }

    let mut remaining = budget_tokens;
    let mut step_index: i64 = 0;
    let mut selection_log: Vec<Value> = Vec::new();
    let mut quorum_trace: Vec<Value> = Vec::new();
    let mut flags: Vec<Value> = Vec::new();

    fn frozen_arm(freezes: &[Value], current_day: i64, arm: &str) -> bool {
        for inc in freezes {
            if inc.get("kind").and_then(Value::as_str) != Some("arm_freeze") {
                continue;
            }
            if inc.get("arm_id").and_then(Value::as_str) != Some(arm) {
                continue;
            }
            let thaw = inc.get("thaw_day").and_then(Value::as_i64).unwrap_or(0);
            if current_day < thaw {
                return true;
            }
        }
        false
    }

    fn relief_sum(reliefs: &[Value], round_id: &str) -> i64 {
        let mut s = 0i64;
        for inc in reliefs {
            if inc.get("kind").and_then(Value::as_str) != Some("quorum_relief") {
                continue;
            }
            if inc.get("round_id").and_then(Value::as_str) != Some(round_id) {
                continue;
            }
            s += inc.get("relief").and_then(Value::as_i64).unwrap_or(0);
        }
        s
    }

    for round in &rounds {
        let relief_applied = relief_sum(&reliefs, &round.round_id);
        let required_distinct = (quorum_distinct - relief_applied).max(1);

        for pull in &round.pulls {
            let votes = pull
                .get("votes")
                .and_then(Value::as_array)
                .ok_or("pull.votes must be array")?;

            // Pre-validate raters exist
            for v in votes {
                let rid = v
                    .get("rater_id")
                    .and_then(Value::as_str)
                    .ok_or("vote.rater_id missing")?;
                if !rater_weights.contains_key(rid) {
                    return Err(format!("unknown rater_id {rid}"));
                }
                let _lab = as_i64(v.get("label").ok_or("vote.label missing")?, "vote.label")?;
                if _lab != 0 && _lab != 1 {
                    return Err("vote.label must be 0 or 1".into());
                }
            }

            // score all candidates
            let mut scores_map: BTreeMap<String, i64> = BTreeMap::new();
            for c in &round.candidates {
                let st = arms.get(c).ok_or_else(|| format!("internal missing arm {c}"))?;
                let sc = score_arm(
                    st.alpha,
                    st.beta,
                    seed,
                    &round.round_id,
                    &round.phase_token,
                    step_index,
                    c,
                );
                scores_map.insert(c.clone(), sc);
            }

            // choose eligible
            let mut best: Option<String> = None;
            let mut best_score: i64 = i64::MIN;
            for c in &round.candidates {
                let st = arms.get(c).unwrap();
                if frozen_arm(&freezes, current_day, c) {
                    continue;
                }
                if st.pull_cost > remaining {
                    continue;
                }
                let sc = *scores_map.get(c).unwrap();
                if sc > best_score {
                    best_score = sc;
                    best = Some(c.clone());
                } else if sc == best_score {
                    let cur = best.as_deref().unwrap_or("");
                    if c.as_str() < cur {
                        best = Some(c.clone());
                    }
                }
            }

            let chosen = best;
            let mut budget_after = remaining;

            if chosen.is_none() {
                let scores_obj: Map<String, Value> = scores_map
                    .iter()
                    .map(|(k, v)| (k.clone(), Value::Number(Number::from(*v))))
                    .collect();
                selection_log.push(sort_value_keys(&serde_json::json!({
                    "budget_after": budget_after,
                    "chosen_arm": Value::Null,
                    "round_id": round.round_id,
                    "scores": Value::Object(scores_obj),
                    "step_index": step_index,
                    "void_reason": "no_eligible_arm",
                })));
                step_index += 1;
                continue;
            }

            let arm_id = chosen.clone().unwrap();
            let cost = arms.get(&arm_id).unwrap().pull_cost;
            remaining -= cost;
            budget_after = remaining;
            arms.get_mut(&arm_id).unwrap().selections += 1;

            // quorum
            let mut distinct: BTreeSet<String> = BTreeSet::new();
            for v in votes {
                distinct.insert(v.get("rater_id").and_then(Value::as_str).unwrap().to_string());
            }
            let distinct_n = distinct.len() as i64;

            let mut w0: i64 = 0;
            let mut w1: i64 = 0;
            for v in votes {
                let rid = v.get("rater_id").and_then(Value::as_str).unwrap();
                let lab = as_i64(v.get("label").unwrap(), "label")?;
                let w = *rater_weights.get(rid).unwrap();
                if lab == 1 {
                    w1 += w;
                } else {
                    w0 += w;
                }
            }

            let mut outcome: Option<i64> = None;
            let mut winner: Option<&'static str> = None;
            let mut vreason: Option<String> = None;

            if distinct_n < required_distinct {
                vreason = Some("insufficient_quorum".into());
                arms.get_mut(&arm_id).unwrap().voids += 1;
            } else if w1 == w0 {
                vreason = Some("tie_vote".into());
                arms.get_mut(&arm_id).unwrap().voids += 1;
            } else if w1 > w0 {
                outcome = Some(1);
                winner = Some("one");
                let st = arms.get_mut(&arm_id).unwrap();
                st.alpha += 1;
                st.successes += 1;
            } else {
                outcome = Some(0);
                winner = Some("zero");
                let st = arms.get_mut(&arm_id).unwrap();
                st.beta += 1;
            }

            if vreason.is_some() {
                flags.push(sort_value_keys(&serde_json::json!({
                    "code": "quorum_void",
                    "detail": vreason.clone().unwrap(),
                    "round_id": round.round_id,
                    "step_index": step_index,
                })));
            }

            if remaining == 0 {
                flags.push(sort_value_keys(&serde_json::json!({
                    "code": "budget_exhausted",
                    "detail": "remaining_budget=0",
                    "round_id": round.round_id,
                    "step_index": step_index,
                })));
            }

            let scores_val: Map<String, Value> = scores_map
                .iter()
                .map(|(k, v)| (k.clone(), Value::Number(Number::from(*v))))
                .collect();
            let void_field = vreason.clone().map(Value::String).unwrap_or(Value::Null);
            let mut sl = Map::new();
            sl.insert(
                "budget_after".to_string(),
                Value::Number(Number::from(budget_after)),
            );
            sl.insert("chosen_arm".to_string(), Value::String(arm_id.clone()));
            sl.insert("round_id".to_string(), Value::String(round.round_id.clone()));
            sl.insert("scores".to_string(), Value::Object(scores_val));
            sl.insert(
                "step_index".to_string(),
                Value::Number(Number::from(step_index)),
            );
            sl.insert("void_reason".to_string(), void_field);
            selection_log.push(sort_value_keys(&Value::Object(sl)));

            let weighted_winner = winner.map(|s| Value::String(s.to_string())).unwrap_or(Value::Null);
            let outv = outcome.map(|n| Value::Number(Number::from(n))).unwrap_or(Value::Null);
            quorum_trace.push(sort_value_keys(&serde_json::json!({
                "chosen_arm": arm_id,
                "distinct_raters": distinct_n,
                "label_one_weight": w1,
                "label_zero_weight": w0,
                "outcome": outv,
                "relief_applied": relief_applied,
                "required_distinct": required_distinct,
                "round_id": round.round_id,
                "step_index": step_index,
                "void_reason": vreason.clone().map(Value::String).unwrap_or(Value::Null),
                "weighted_winner": weighted_winner,
            })));

            step_index += 1;
        }
    }

    flags.sort_by(|a, b| {
        let ca = a.get("code").and_then(Value::as_str).unwrap();
        let cb = b.get("code").and_then(Value::as_str).unwrap();
        ca.cmp(cb).then_with(|| {
            let ra = a.get("round_id").and_then(Value::as_str).unwrap();
            let rb = b.get("round_id").and_then(Value::as_str).unwrap();
            ra.cmp(rb)
        }).then_with(|| {
            let sa = a.get("step_index").and_then(Value::as_i64).unwrap();
            let sb = b.get("step_index").and_then(Value::as_i64).unwrap();
            sa.cmp(&sb)
        }).then_with(|| {
            let da = a.get("detail").and_then(Value::as_str).unwrap();
            let db = b.get("detail").and_then(Value::as_str).unwrap();
            da.cmp(db)
        })
    });

    let mut arms_out: Vec<Value> = Vec::new();
    for (_id, arm) in arms.iter() {
        arms_out.push(sort_value_keys(&serde_json::json!({
            "alpha": arm.alpha,
            "arm_id": arm.arm_id,
            "beta": arm.beta,
            "pull_cost": arm.pull_cost,
            "selections": arm.selections,
            "start_alpha": arm.start_alpha,
            "start_beta": arm.start_beta,
            "successes": arm.successes,
            "voids": arm.voids,
        })));
    }

    let mut supported_sorted = supported_kinds.clone();
    supported_sorted.sort();

    let void_steps = selection_log
        .iter()
        .filter(|row| row.get("void_reason").map(|v| !v.is_null()).unwrap_or(false))
        .count() as i64;

    let summary = sort_value_keys(&serde_json::json!({
        "active_incidents": active,
        "arms_total": arms.len() as i64,
        "audit_schema_version": audit_schema,
        "audit_version": audit_version,
        "budget_remaining": remaining,
        "current_day": current_day,
        "flags_total": flags.len() as i64,
        "ignored_incidents": ignored,
        "round_files": rounds.len() as i64,
        "supported_incident_kinds": supported_sorted,
        "total_steps": step_index,
        "void_steps": void_steps,
    }));

    write_json(&out.join("selection_log.json"), &Value::Array(selection_log))?;
    write_json(&out.join("quorum_trace.json"), &Value::Array(quorum_trace))?;
    let flags_obj = sort_value_keys(&serde_json::json!({ "flags": flags }));
    write_json(&out.join("flags.json"), &flags_obj)?;
    let posterior = sort_value_keys(&serde_json::json!({ "arms": arms_out }));
    write_json(&out.join("posterior_report.json"), &posterior)?;
    write_json(&out.join("summary.json"), &summary)?;
    Ok(())
}