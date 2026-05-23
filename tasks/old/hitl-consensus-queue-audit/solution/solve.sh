#!/bin/bash
set -euo pipefail

mkdir -p "${HCQ_AUDIT_DIR:-/app/audit}"

cat <<'HCQ_ORACLE_RS_EOF_MARKER' > /app/auditor/src/main.rs
use serde_json::{Map, Value};
use std::collections::BTreeMap;
use std::collections::BTreeSet;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

fn kind_supported(k: &str) -> bool {
    matches!(k, "weight_scaler" | "quorum_bump" | "batch_freeze")
}

fn data_dir() -> PathBuf {
    env::var("HCQ_DATA_DIR")
        .unwrap_or_else(|_| "/app/hitl".to_string())
        .into()
}

fn audit_dir() -> PathBuf {
    env::var("HCQ_AUDIT_DIR")
        .unwrap_or_else(|_| "/app/audit".to_string())
        .into()
}

fn read_json(path: &Path) -> Value {
    let text =
        fs::read_to_string(path).unwrap_or_else(|e| panic!("read {}: {}", path.display(), e));
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("parse {}: {}", path.display(), e))
}

fn load_dir(dir: &Path) -> Vec<Value> {
    let mut rows = Vec::new();
    if !dir.is_dir() {
        return rows;
    }
    let mut paths: Vec<PathBuf> = fs::read_dir(dir)
        .unwrap()
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|x| x.to_str()) == Some("json"))
        .collect();
    paths.sort();
    for p in paths {
        rows.push(read_json(&p));
    }
    rows
}

fn sort_keys(v: &Value) -> Value {
    match v {
        Value::Object(m) => {
            let mut keys: Vec<String> = m.keys().cloned().collect();
            keys.sort();
            let mut out = Map::new();
            for k in keys {
                if let Some(c) = m.get(&k) {
                    out.insert(k, sort_keys(c));
                }
            }
            Value::Object(out)
        }
        Value::Array(a) => Value::Array(a.iter().map(sort_keys).collect()),
        _ => v.clone(),
    }
}

fn write_json(path: &Path, v: &Value) {
    let sorted = sort_keys(v);
    let mut s = serde_json::to_string_pretty(&sorted).expect("serialize");
    s.push('\n');
    fs::write(path, s).expect("write");
}

fn is_active(inc: &Value, current_day: i64) -> bool {
    if !inc.get("accepted").and_then(Value::as_bool).unwrap_or(false) {
        return false;
    }
    if inc.get("day").and_then(Value::as_i64).unwrap_or(-1) > current_day {
        return false;
    }
    inc.get("kind")
        .and_then(Value::as_str)
        .map(kind_supported)
        .unwrap_or(false)
}

fn extra_quorum(active: &[Value], batch_id: &str) -> i64 {
    let mut extra = 0i64;
    for inc in active {
        if inc.get("kind").and_then(Value::as_str) != Some("quorum_bump") {
            continue;
        }
        let Some(bids) = inc.get("batch_ids").and_then(Value::as_array) else {
            continue;
        };
        if bids
            .iter()
            .any(|b| b.as_str().map(|s| s == batch_id).unwrap_or(false))
        {
            extra += inc
                .get("extra_distinct")
                .and_then(Value::as_i64)
                .unwrap_or(0);
        }
    }
    extra
}

fn compose_scalers_for_vote(active: &[Value], aid: &str, vote_day: i64) -> Vec<Value> {
    let mut applied = Vec::new();
    for inc in active {
        if inc.get("kind").and_then(Value::as_str) != Some("weight_scaler") {
            continue;
        }
        if inc
            .get("annotator_id")
            .and_then(Value::as_str)
            .unwrap_or("")
            != aid
        {
            continue;
        }
        if vote_day < inc.get("effective_day").and_then(Value::as_i64).unwrap_or(0) {
            continue;
        }
        applied.push(inc.clone());
    }
    applied.sort_by(|a, b| {
        let da = a.get("day").and_then(Value::as_i64).unwrap_or(0);
        let db = b.get("day").and_then(Value::as_i64).unwrap_or(0);
        da.cmp(&db).then_with(|| {
            let ea = a.get("event_id").and_then(Value::as_str).unwrap_or("");
            let eb = b.get("event_id").and_then(Value::as_str).unwrap_or("");
            ea.cmp(eb)
        })
    });
    applied
}

fn active_scalers_for_annotator(active: &[Value], aid: &str, current_day: i64) -> Vec<Value> {
    let mut scalers = Vec::new();
    for inc in active {
        if inc.get("kind").and_then(Value::as_str) != Some("weight_scaler") {
            continue;
        }
        if inc
            .get("annotator_id")
            .and_then(Value::as_str)
            .unwrap_or("")
            != aid
        {
            continue;
        }
        if inc
            .get("effective_day")
            .and_then(Value::as_i64)
            .unwrap_or(0)
            > current_day
        {
            continue;
        }
        scalers.push(inc.clone());
    }
    scalers.sort_by(|a, b| {
        let da = a.get("day").and_then(Value::as_i64).unwrap_or(0);
        let db = b.get("day").and_then(Value::as_i64).unwrap_or(0);
        da.cmp(&db).then_with(|| {
            let ea = a.get("event_id").and_then(Value::as_str).unwrap_or("");
            let eb = b.get("event_id").and_then(Value::as_str).unwrap_or("");
            ea.cmp(eb)
        })
    });
    scalers
        .into_iter()
        .map(|x| {
            serde_json::json!({
                "event_id": x.get("event_id").and_then(Value::as_str).unwrap_or(""),
                "pct_den": x.get("pct_den").and_then(Value::as_i64).unwrap_or(1),
                "pct_num": x.get("pct_num").and_then(Value::as_i64).unwrap_or(1),
            })
        })
        .collect()
}

fn vote_weight(
    annotators: &BTreeMap<String, Value>,
    tier_weight: &BTreeMap<String, i64>,
    active: &[Value],
    gold_mismatch: &BTreeSet<String>,
    aid: &str,
    vote_day: i64,
) -> i64 {
    let ann = annotators.get(aid).expect("annotator");
    let tier = ann.get("tier").and_then(Value::as_str).unwrap();
    let mut w = *tier_weight.get(tier).expect("tier_weight");
    for inc in compose_scalers_for_vote(active, aid, vote_day) {
        let num = inc.get("pct_num").and_then(Value::as_i64).unwrap_or(1);
        let den = inc.get("pct_den").and_then(Value::as_i64).unwrap_or(1);
        w = w * num / den;
    }
    if gold_mismatch.contains(aid) {
        w /= 2;
    }
    if w == 0 {
        w = 1;
    }
    w
}

fn resolve_open(
    it: &Value,
    frozen_batches: &BTreeSet<String>,
    annotators: &BTreeMap<String, Value>,
    tier_weight: &BTreeMap<String, i64>,
    active: &[Value],
    gold_mismatch: &BTreeSet<String>,
    abstain: &str,
    min_distinct: i64,
    min_winner_weight: i64,
) -> Value {
    let bid = it.get("batch_id").and_then(Value::as_str).unwrap();
    if frozen_batches.contains(bid) {
        return serde_json::json!({
            "batch_id": bid,
            "distinct_voters": 0,
            "final_label": Value::Null,
            "item_id": it.get("item_id").and_then(Value::as_str).unwrap(),
            "required_distinct": 0,
            "runner_up_label": Value::Null,
            "status": "blocked_freeze",
            "winner_weight": 0,
        });
    }

    let required = min_distinct + extra_quorum(active, bid);
    let votes = it.get("votes").and_then(Value::as_array).cloned().unwrap_or_default();
    let non_abs: Vec<&Value> = votes
        .iter()
        .filter(|v| v.get("label").and_then(Value::as_str).unwrap_or("") != abstain)
        .collect();

    let mut distinct_set = BTreeSet::new();
    for v in &non_abs {
        distinct_set.insert(v.get("annotator_id").and_then(Value::as_str).unwrap().to_string());
    }
    let distinct: Vec<String> = distinct_set.into_iter().collect();

    if (distinct.len() as i64) < required {
        return serde_json::json!({
            "batch_id": bid,
            "distinct_voters": distinct.len(),
            "final_label": Value::Null,
            "item_id": it.get("item_id").and_then(Value::as_str).unwrap(),
            "required_distinct": required,
            "runner_up_label": Value::Null,
            "status": "insufficient_quorum",
            "winner_weight": 0,
        });
    }

    let mut sums: BTreeMap<String, i64> = BTreeMap::new();
    for v in &non_abs {
        let lab = v.get("label").and_then(Value::as_str).unwrap().to_string();
        let aid = v.get("annotator_id").and_then(Value::as_str).unwrap();
        let vote_day = v.get("day").and_then(Value::as_i64).unwrap();
        let w = vote_weight(annotators, tier_weight, active, gold_mismatch, aid, vote_day);
        *sums.entry(lab).or_insert(0) += w;
    }

    let max_sum = *sums.values().max().unwrap_or(&0);
    let mut winners: Vec<&String> = sums.iter().filter(|(_, s)| **s == max_sum).map(|(l, _)| l).collect();
    winners.sort();
    let winner = winners[0].clone();
    let winner_sum = sums[&winner];

    let uniq_vals: BTreeSet<i64> = sums.values().copied().collect();
    let mut uniq: Vec<i64> = uniq_vals.into_iter().collect();
    uniq.sort_by(|a, b| b.cmp(a));

    let runner = if uniq.len() < 2 {
        Value::Null
    } else {
        let second = uniq[1];
        let mut labs: Vec<&String> = sums
            .iter()
            .filter(|(_, s)| **s == second)
            .map(|(l, _)| l)
            .collect();
        labs.sort();
        Value::String(labs[0].clone())
    };

    let status = if winner_sum < min_winner_weight {
        "low_confidence"
    } else {
        "resolved"
    };

    serde_json::json!({
        "batch_id": bid,
        "distinct_voters": distinct.len(),
        "final_label": winner,
        "item_id": it.get("item_id").and_then(Value::as_str).unwrap(),
        "required_distinct": required,
        "runner_up_label": runner,
        "status": status,
        "winner_weight": winner_sum,
    })
}

fn resolve_gold(it: &Value, frozen_batches: &BTreeSet<String>) -> Value {
    let bid = it.get("batch_id").and_then(Value::as_str).unwrap();
    if frozen_batches.contains(bid) {
        return serde_json::json!({
            "batch_id": bid,
            "distinct_voters": 0,
            "final_label": Value::Null,
            "item_id": it.get("item_id").and_then(Value::as_str).unwrap(),
            "required_distinct": 0,
            "runner_up_label": Value::Null,
            "status": "blocked_freeze",
            "winner_weight": 0,
        });
    }
    let votes = it.get("votes").and_then(Value::as_array).cloned().unwrap_or_default();
    let mut distinct_all = BTreeSet::new();
    for v in &votes {
        distinct_all.insert(v.get("annotator_id").and_then(Value::as_str).unwrap().to_string());
    }
    serde_json::json!({
        "batch_id": bid,
        "distinct_voters": distinct_all.len(),
        "final_label": it.get("gold_label").and_then(Value::as_str).unwrap(),
        "item_id": it.get("item_id").and_then(Value::as_str).unwrap(),
        "required_distinct": 0,
        "runner_up_label": Value::Null,
        "status": "gold_locked",
        "winner_weight": 0,
    })
}

fn main() {
    let data = data_dir();
    let out = audit_dir();
    fs::create_dir_all(&out).expect("mkdir audit");

    let pool = read_json(&data.join("pool_state.json"));
    let policy = read_json(&data.join("policy.json"));
    let incident_root = read_json(&data.join("incident_log.json"));
    let incidents = incident_root
        .get("incidents")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    let mut annotators: BTreeMap<String, Value> = BTreeMap::new();
    for r in load_dir(&data.join("annotators")) {
        let id = r.get("annotator_id").and_then(Value::as_str).unwrap().to_string();
        annotators.insert(id, r);
    }

    let mut batches: BTreeMap<String, Value> = BTreeMap::new();
    for r in load_dir(&data.join("batches")) {
        let id = r.get("batch_id").and_then(Value::as_str).unwrap().to_string();
        batches.insert(id, r);
    }

    let mut items = load_dir(&data.join("items"));

    let current_day = pool.get("current_day").and_then(Value::as_i64).unwrap();
    let audit_version = pool.get("audit_version").and_then(Value::as_str).unwrap();
    let abstain = policy.get("abstain_token").and_then(Value::as_str).unwrap();
    let min_distinct = policy
        .get("min_distinct_labelers")
        .and_then(Value::as_i64)
        .unwrap();
    let min_winner_weight = policy
        .get("min_winner_weight")
        .and_then(Value::as_i64)
        .unwrap();

    let mut tier_weight: BTreeMap<String, i64> = BTreeMap::new();
    if let Some(tw) = policy.get("tier_weight").and_then(Value::as_object) {
        for (k, v) in tw {
            tier_weight.insert(k.clone(), v.as_i64().unwrap());
        }
    }

    let active_incidents: Vec<Value> = incidents
        .iter()
        .filter(|i| is_active(i, current_day))
        .cloned()
        .collect();
    let ignored_incidents = incidents.len() - active_incidents.len();

    let mut frozen_batches = BTreeSet::new();
    for inc in &active_incidents {
        if inc.get("kind").and_then(Value::as_str) == Some("batch_freeze") {
            if current_day < inc.get("thaw_day").and_then(Value::as_i64).unwrap_or(0) {
                frozen_batches.insert(
                    inc.get("batch_id")
                        .and_then(Value::as_str)
                        .unwrap()
                        .to_string(),
                );
            }
        }
    }

    let mut gold_mismatch = BTreeSet::new();
    for it in &items {
        if !it
            .get("is_calibration_gold")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            continue;
        }
        let gold_label = it.get("gold_label").and_then(Value::as_str).unwrap();
        if let Some(votes) = it.get("votes").and_then(Value::as_array) {
            for v in votes {
                let lab = v.get("label").and_then(Value::as_str).unwrap();
                if lab == abstain {
                    continue;
                }
                if lab != gold_label {
                    gold_mismatch.insert(
                        v.get("annotator_id")
                            .and_then(Value::as_str)
                            .unwrap()
                            .to_string(),
                    );
                }
            }
        }
    }

    items.sort_by(|a, b| {
        let ia = a.get("item_id").and_then(Value::as_str).unwrap();
        let ib = b.get("item_id").and_then(Value::as_str).unwrap();
        ia.cmp(ib)
    });

    let mut consensus_items = Vec::new();
    for it in &items {
        let row = if it
            .get("is_calibration_gold")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            resolve_gold(it, &frozen_batches)
        } else {
            resolve_open(
                it,
                &frozen_batches,
                &annotators,
                &tier_weight,
                &active_incidents,
                &gold_mismatch,
                abstain,
                min_distinct,
                min_winner_weight,
            )
        };
        consensus_items.push(row);
    }

    write_json(
        &out.join("consensus_report.json"),
        &serde_json::json!({ "items": consensus_items }),
    );

    let mut by_status: BTreeMap<String, i64> = BTreeMap::new();
    for row in &consensus_items {
        let st = row.get("status").and_then(Value::as_str).unwrap().to_string();
        *by_status.entry(st).or_insert(0) += 1;
    }

    let mut items_by_id: BTreeMap<String, Value> = BTreeMap::new();
    for it in &items {
        let id = it.get("item_id").and_then(Value::as_str).unwrap().to_string();
        items_by_id.insert(id, it.clone());
    }

    let mut eligible = Vec::new();
    for row in &consensus_items {
        let st = row.get("status").and_then(Value::as_str).unwrap();
        if st == "blocked_freeze" || st == "insufficient_quorum" {
            continue;
        }
        let item_id = row.get("item_id").and_then(Value::as_str).unwrap();
        let it = items_by_id.get(item_id).unwrap();
        let bid = it.get("batch_id").and_then(Value::as_str).unwrap();
        let btier = batches
            .get(bid)
            .unwrap()
            .get("business_tier")
            .and_then(Value::as_i64)
            .unwrap();
        let vote_days: Vec<i64> = it
            .get("votes")
            .and_then(Value::as_array)
            .map(|arr| {
                arr.iter()
                    .map(|v| v.get("day").and_then(Value::as_i64).unwrap_or(0))
                    .collect()
            })
            .unwrap_or_default();
        let eligible_day = vote_days.iter().copied().min().unwrap_or(0);
        eligible.push(serde_json::json!({
            "batch_id": bid,
            "business_tier": btier,
            "eligible_day": eligible_day,
            "item_id": item_id,
        }));
    }

    eligible.sort_by(|a, b| {
        let ea = a.get("eligible_day").and_then(Value::as_i64).unwrap();
        let eb = b.get("eligible_day").and_then(Value::as_i64).unwrap();
        ea.cmp(&eb)
            .then_with(|| {
                let ta = a.get("business_tier").and_then(Value::as_i64).unwrap();
                let tb = b.get("business_tier").and_then(Value::as_i64).unwrap();
                ta.cmp(&tb)
            })
            .then_with(|| {
                let ba = a.get("batch_id").and_then(Value::as_str).unwrap();
                let bb = b.get("batch_id").and_then(Value::as_str).unwrap();
                ba.cmp(bb)
            })
            .then_with(|| {
                let ia = a.get("item_id").and_then(Value::as_str).unwrap();
                let ib = b.get("item_id").and_then(Value::as_str).unwrap();
                ia.cmp(ib)
            })
    });

    let mut backlog = Vec::new();
    for (idx, e) in eligible.iter().enumerate() {
        backlog.push(serde_json::json!({
            "batch_id": e.get("batch_id").unwrap(),
            "business_tier": e.get("business_tier").unwrap(),
            "eligible_day": e.get("eligible_day").unwrap(),
            "item_id": e.get("item_id").unwrap(),
            "rank": (idx + 1) as i64,
        }));
    }

    write_json(
        &out.join("queue_order.json"),
        &serde_json::json!({ "backlog": backlog }),
    );

    let mut reliability = Vec::new();
    for (aid, ann) in &annotators {
        let mut gd = 0i64;
        for it in &items {
            if !it
                .get("is_calibration_gold")
                .and_then(Value::as_bool)
                .unwrap_or(false)
            {
                continue;
            }
            let gl = it.get("gold_label").and_then(Value::as_str).unwrap();
            if let Some(votes) = it.get("votes").and_then(Value::as_array) {
                for v in votes {
                    if v.get("annotator_id").and_then(Value::as_str).unwrap_or("") != aid {
                        continue;
                    }
                    let lab = v.get("label").and_then(Value::as_str).unwrap();
                    if lab == abstain {
                        continue;
                    }
                    if lab != gl {
                        gd += 1;
                    }
                }
            }
        }
        let scalers = active_scalers_for_annotator(&active_incidents, aid, current_day);
        reliability.push(serde_json::json!({
            "active_scalers": scalers,
            "annotator_id": aid,
            "gold_disagreements": gd,
            "tier": ann.get("tier").and_then(Value::as_str).unwrap(),
            "weight_halved": gold_mismatch.contains(aid.as_str()),
        }));
    }

    write_json(
        &out.join("annotator_reliability.json"),
        &serde_json::json!({ "annotators": reliability }),
    );

    let mut flags = Vec::new();
    for row in &consensus_items {
        let st = row.get("status").and_then(Value::as_str).unwrap();
        let item_id = row.get("item_id").and_then(Value::as_str).unwrap();
        if st == "blocked_freeze" {
            let bid = row.get("batch_id").and_then(Value::as_str).unwrap();
            flags.push(serde_json::json!({
                "code": "freeze_active",
                "detail": format!("batch={bid}"),
                "item_id": item_id,
            }));
        } else if st == "insufficient_quorum" {
            let req = row.get("required_distinct").and_then(Value::as_i64).unwrap();
            flags.push(serde_json::json!({
                "code": "quorum_shortfall",
                "detail": format!("need>={req}"),
                "item_id": item_id,
            }));
        }
    }

    flags.sort_by(|a, b| {
        let ca = a.get("code").and_then(Value::as_str).unwrap();
        let cb = b.get("code").and_then(Value::as_str).unwrap();
        ca.cmp(cb).then_with(|| {
            let ia = a.get("item_id").and_then(Value::as_str).unwrap();
            let ib = b.get("item_id").and_then(Value::as_str).unwrap();
            ia.cmp(ib)
        })
    });

    write_json(
        &out.join("compliance_flags.json"),
        &serde_json::json!({ "flags": flags }),
    );

    let open_items = items
        .iter()
        .filter(|it| {
            !it
                .get("is_calibration_gold")
                .and_then(Value::as_bool)
                .unwrap_or(false)
        })
        .count() as i64;
    let gold_items = items
        .iter()
        .filter(|it| {
            it.get("is_calibration_gold")
                .and_then(Value::as_bool)
                .unwrap_or(false)
        })
        .count() as i64;

    let blocked_batches: Vec<Value> = frozen_batches
        .iter()
        .map(|s| Value::String(s.clone()))
        .collect();

    let summary = serde_json::json!({
        "audit_version": audit_version,
        "blocked_batches": blocked_batches,
        "by_status": by_status,
        "current_day": current_day,
        "ignored_incidents": ignored_incidents,
        "totals": {
            "active_incidents": active_incidents.len() as i64,
            "gold_items": gold_items,
            "items_total": items.len() as i64,
            "open_items": open_items,
        },
    });

    write_json(&out.join("summary.json"), &summary);
}

HCQ_ORACLE_RS_EOF_MARKER

cd /app/auditor
cargo build --quiet --release
cp /app/auditor/target/release/hitl_consensus_queue_audit /app/bin/hcq-auditor
HCQ_DATA_DIR="${HCQ_DATA_DIR:-/app/hitl}" HCQ_AUDIT_DIR="${HCQ_AUDIT_DIR:-/app/audit}" /app/bin/hcq-auditor
