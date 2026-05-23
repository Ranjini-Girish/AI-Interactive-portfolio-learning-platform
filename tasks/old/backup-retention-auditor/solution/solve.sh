#!/bin/bash
set -euo pipefail

AUDITOR_DIR="${BRA_AUDITOR_DIR:-/app/auditor}"
AUDIT_DIR="${BRA_AUDIT_DIR:-/app/audit}"

mkdir -p "$AUDIT_DIR"

cat > "$AUDITOR_DIR/src/main.rs" <<'AUDITOR_RS_EOF'
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{json, Map, Number, Value};

fn tier_rank(tier: &str) -> i64 {
    match tier {
        "bronze" => 0,
        "silver" => 1,
        "gold" => 2,
        _ => 99,
    }
}

fn is_hex64(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

fn read_json(path: &Path) -> Value {
    let text = fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("read {}: {}", path.display(), e));
    serde_json::from_str(&text)
        .unwrap_or_else(|e| panic!("parse {}: {}", path.display(), e))
}

fn write_json(path: &Path, val: &Value) {
    let mut text = serde_json::to_string_pretty(val)
        .expect("serialize failed");
    text.push('\n');
    fs::write(path, text).expect("write failed");
}

fn data_dir() -> PathBuf {
    env::var("BRA_DATA_DIR")
        .unwrap_or_else(|_| "/app/data".to_string())
        .into()
}

fn out_dir() -> PathBuf {
    env::var("BRA_AUDIT_DIR")
        .unwrap_or_else(|_| "/app/audit".to_string())
        .into()
}

fn is_valid_snapshot(s: &Value, current_day: i64) -> bool {
    if !matches!(s.get("id"), Some(Value::String(x)) if !x.is_empty()) {
        return false;
    }
    let kind = s.get("kind").and_then(Value::as_str);
    if !matches!(kind, Some("full") | Some("incremental")) {
        return false;
    }
    let td = match s.get("taken_day").and_then(Value::as_i64) {
        Some(x) => x,
        None => return false,
    };
    if td < 0 || td > current_day {
        return false;
    }
    let sm = match s.get("size_mb").and_then(Value::as_i64) {
        Some(x) => x,
        None => return false,
    };
    if sm < 0 {
        return false;
    }
    if !matches!(s.get("sha256_chain"), Some(Value::String(x)) if is_hex64(x)) {
        return false;
    }
    if kind == Some("incremental")
        && !matches!(s.get("parent_id"), Some(Value::String(x)) if !x.is_empty())
    {
        return false;
    }
    true
}

fn bucket_index(taken_day: i64, kind: &str) -> Option<i64> {
    match kind {
        "daily" => Some(taken_day),
        "weekly" => Some(taken_day / 7),
        "monthly" => Some(taken_day / 30),
        "yearly" => Some(taken_day / 365),
        _ => None,
    }
}

fn evaluate_rule(rule: &Value, candidates: &[Value], current_day: i64) -> BTreeSet<String> {
    let kind = rule.get("kind").and_then(Value::as_str).unwrap_or("");
    let keep_count = rule.get("keep_count").and_then(Value::as_i64).unwrap_or(0);
    let max_age = rule.get("max_age_days").and_then(Value::as_i64).unwrap_or(0);
    if keep_count <= 0 {
        return BTreeSet::new();
    }
    let mut buckets: BTreeMap<i64, (String, i64)> = BTreeMap::new();
    for s in candidates {
        let td = s.get("taken_day").and_then(Value::as_i64).unwrap();
        if current_day - td > max_age {
            continue;
        }
        let id = s.get("id").and_then(Value::as_str).unwrap().to_string();
        let b = match bucket_index(td, kind) {
            Some(b) => b,
            None => continue,
        };
        match buckets.get(&b) {
            None => {
                buckets.insert(b, (id, td));
            }
            Some((cur_id, cur_td)) => {
                let better = td > *cur_td || (td == *cur_td && id < *cur_id);
                if better {
                    buckets.insert(b, (id, td));
                }
            }
        }
    }
    let mut keys: Vec<i64> = buckets.keys().copied().collect();
    keys.sort_by(|a, b| b.cmp(a));
    let mut selected: BTreeSet<String> = BTreeSet::new();
    for k in keys.iter().take(keep_count as usize) {
        selected.insert(buckets[k].0.clone());
    }
    selected
}

fn effective_rules(profile: &Value, global: &[Value]) -> Vec<Value> {
    let empty: Vec<Value> = vec![];
    let overrides_raw = profile
        .get("override_rules")
        .and_then(|v| v.as_array())
        .unwrap_or(&empty);
    let mut by_kind: BTreeMap<String, Value> = BTreeMap::new();
    for r in overrides_raw {
        let k = r.get("kind").and_then(Value::as_str).unwrap_or("").to_string();
        by_kind.insert(k, r.clone());
    }
    let overridden: BTreeSet<String> = by_kind.keys().cloned().collect();
    let mut effective: Vec<Value> = global
        .iter()
        .filter(|r| {
            let k = r.get("kind").and_then(Value::as_str).unwrap_or("").to_string();
            !overridden.contains(&k)
        })
        .cloned()
        .collect();
    effective.extend(by_kind.into_values());
    effective
}

fn applies_to_host(rule: &Value, tier: &str) -> bool {
    let at = rule
        .get("applies_to_tier")
        .and_then(Value::as_str)
        .unwrap_or("*");
    at == "*" || at == tier
}

fn list_sorted_json_files(dir: &Path) -> Vec<PathBuf> {
    let mut entries: Vec<PathBuf> = fs::read_dir(dir)
        .unwrap_or_else(|e| panic!("read_dir {}: {}", dir.display(), e))
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|s| s.to_str()) == Some("json"))
        .collect();
    entries.sort();
    entries
}

fn main() {
    let data = data_dir();
    let out = out_dir();
    fs::create_dir_all(&out).expect("create audit dir");

    let pool = read_json(&data.join("pool_state.json"));
    let capacity_mb = pool.get("capacity_mb").and_then(Value::as_i64).unwrap();
    let current_day = pool.get("current_day").and_then(Value::as_i64).unwrap();
    let tier_quotas: BTreeMap<String, i64> = pool
        .get("tier_quotas")
        .and_then(|v| v.as_object())
        .unwrap()
        .iter()
        .map(|(k, v)| (k.clone(), v.as_i64().unwrap()))
        .collect();

    let policy = read_json(&data.join("retention_policy.json"));
    let global_rules: Vec<Value> = policy
        .get("rules")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut profile_by_host: BTreeMap<String, Value> = BTreeMap::new();
    for p in list_sorted_json_files(&data.join("host_profiles")) {
        let v = read_json(&p);
        let host = v.get("host").and_then(Value::as_str).unwrap().to_string();
        profile_by_host.insert(host, v);
    }

    let mut snaps_by_host: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    for p in list_sorted_json_files(&data.join("snapshots")) {
        let v = read_json(&p);
        let host = v.get("host").and_then(Value::as_str).unwrap().to_string();
        let snaps = v
            .get("snapshots")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        snaps_by_host.insert(host, snaps);
    }

    let incidents_doc = read_json(&data.join("incident_log.json"));
    let raw_events: Vec<Value> = incidents_doc
        .get("events")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut valid_by_host: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    let mut invalid_count_by_host: BTreeMap<String, i64> = BTreeMap::new();
    let mut all_valid_ids: BTreeSet<String> = BTreeSet::new();
    for (host, snaps) in &snaps_by_host {
        let v: Vec<Value> = snaps
            .iter()
            .filter(|s| is_valid_snapshot(s, current_day))
            .cloned()
            .collect();
        invalid_count_by_host.insert(host.clone(), (snaps.len() - v.len()) as i64);
        for s in &v {
            all_valid_ids.insert(s["id"].as_str().unwrap().to_string());
        }
        valid_by_host.insert(host.clone(), v);
    }

    let mut snap_global_index: BTreeMap<String, (String, Value)> = BTreeMap::new();
    for (host, snaps) in &valid_by_host {
        for s in snaps {
            snap_global_index.insert(
                s["id"].as_str().unwrap().to_string(),
                (host.clone(), s.clone()),
            );
        }
    }

    let allowed_kinds: BTreeSet<&str> = ["tamper", "restore_failure", "chain_break"]
        .iter()
        .copied()
        .collect();
    let mut accepted_events: Vec<Value> = vec![];
    let mut ignored_count: i64 = 0;
    for ev in &raw_events {
        let kind = ev.get("kind").and_then(Value::as_str);
        let day = ev.get("day").and_then(Value::as_i64);
        let sid = ev.get("snapshot_id").and_then(Value::as_str);
        if !matches!(kind, Some(k) if allowed_kinds.contains(k)) {
            ignored_count += 1;
            continue;
        }
        let day = match day {
            Some(d) if d <= current_day => d,
            _ => {
                ignored_count += 1;
                continue;
            }
        };
        let sid_s = match sid {
            Some(s) if all_valid_ids.contains(s) => s.to_string(),
            _ => {
                ignored_count += 1;
                continue;
            }
        };
        let ref_snap = &snap_global_index[&sid_s].1;
        let ref_day = ref_snap.get("taken_day").and_then(Value::as_i64).unwrap();
        if day < ref_day {
            ignored_count += 1;
            continue;
        }
        accepted_events.push(ev.clone());
    }

    let chain_break_ids: BTreeSet<String> = accepted_events
        .iter()
        .filter(|e| e["kind"].as_str() == Some("chain_break"))
        .map(|e| e["snapshot_id"].as_str().unwrap().to_string())
        .collect();
    let tamper_events: Vec<&Value> = accepted_events
        .iter()
        .filter(|e| e["kind"].as_str() == Some("tamper"))
        .collect();
    let tamper_ids: BTreeSet<String> = tamper_events
        .iter()
        .map(|e| e["snapshot_id"].as_str().unwrap().to_string())
        .collect();

    let mut children_by_host: BTreeMap<String, BTreeMap<String, Vec<String>>> = BTreeMap::new();
    for (host, snaps) in &valid_by_host {
        let valid_id_set: BTreeSet<String> = snaps
            .iter()
            .map(|s| s["id"].as_str().unwrap().to_string())
            .collect();
        let map = children_by_host.entry(host.clone()).or_default();
        for s in snaps {
            if s["kind"].as_str() != Some("incremental") {
                continue;
            }
            let pid = match s.get("parent_id").and_then(Value::as_str) {
                Some(x) => x.to_string(),
                None => continue,
            };
            if valid_id_set.contains(&pid) {
                map.entry(pid)
                    .or_default()
                    .push(s["id"].as_str().unwrap().to_string());
            }
        }
    }

    let mut contained_ids: BTreeSet<String> = BTreeSet::new();
    for ev in &tamper_events {
        let sid = ev["snapshot_id"].as_str().unwrap().to_string();
        let (host, root_snap) = &snap_global_index[&sid];
        let window = ev
            .get("containment_window_days")
            .and_then(Value::as_i64)
            .unwrap_or(0);
        let root_day = root_snap.get("taken_day").and_then(Value::as_i64).unwrap();
        contained_ids.insert(sid.clone());
        let host_snap_by_id: BTreeMap<String, Value> = valid_by_host[host]
            .iter()
            .map(|s| (s["id"].as_str().unwrap().to_string(), s.clone()))
            .collect();
        let empty_map: BTreeMap<String, Vec<String>> = BTreeMap::new();
        let host_children = children_by_host.get(host).unwrap_or(&empty_map);
        let mut queue: VecDeque<String> = VecDeque::new();
        queue.push_back(sid.clone());
        let mut visited_locally: BTreeSet<String> = BTreeSet::new();
        visited_locally.insert(sid.clone());
        while let Some(cur) = queue.pop_front() {
            let empty_vec: Vec<String> = vec![];
            for child_id in host_children.get(&cur).unwrap_or(&empty_vec) {
                if !visited_locally.insert(child_id.clone()) {
                    continue;
                }
                let child = &host_snap_by_id[child_id];
                let child_day = child.get("taken_day").and_then(Value::as_i64).unwrap();
                if child_day - root_day <= window {
                    contained_ids.insert(child_id.clone());
                    queue.push_back(child_id.clone());
                }
            }
        }
    }

    let mut retention_kept_ids: BTreeSet<String> = BTreeSet::new();
    let mut matched_rule_for: BTreeMap<String, String> = BTreeMap::new();
    let sorted_hosts: Vec<String> = valid_by_host.keys().cloned().collect();

    for host in &sorted_hosts {
        let profile = match profile_by_host.get(host) {
            Some(p) => p,
            None => continue,
        };
        let valid_snaps = &valid_by_host[host];
        let eligible: Vec<Value> = valid_snaps
            .iter()
            .filter(|s| !contained_ids.contains(s["id"].as_str().unwrap()))
            .cloned()
            .collect();
        if profile.get("exempt").and_then(Value::as_bool).unwrap_or(false) {
            for s in &eligible {
                let id = s["id"].as_str().unwrap().to_string();
                retention_kept_ids.insert(id.clone());
                matched_rule_for.insert(id, "exempt".to_string());
            }
            continue;
        }
        let tier = profile["tier"].as_str().unwrap();
        let rules = effective_rules(profile, &global_rules);
        let applicable_rules: Vec<Value> = rules
            .into_iter()
            .filter(|r| applies_to_host(r, tier))
            .collect();

        let mut per_rule: BTreeMap<String, (i64, BTreeSet<String>)> = BTreeMap::new();
        for r in &applicable_rules {
            let name = r["name"].as_str().unwrap().to_string();
            let pri = r["priority"].as_i64().unwrap();
            let sel = evaluate_rule(r, &eligible, current_day);
            per_rule.insert(name, (pri, sel));
        }

        for s in &eligible {
            let id = s["id"].as_str().unwrap().to_string();
            let mut best: Option<(i64, String)> = None;
            for (rname, (pri, sel)) in &per_rule {
                if sel.contains(&id) {
                    match &best {
                        None => best = Some((*pri, rname.clone())),
                        Some((bp, bn)) => {
                            if *pri < *bp || (*pri == *bp && rname < bn) {
                                best = Some((*pri, rname.clone()));
                            }
                        }
                    }
                }
            }
            if let Some((_, rname)) = best {
                retention_kept_ids.insert(id.clone());
                matched_rule_for.insert(id, rname);
            }
        }
    }

    let mut integrity_per_host: BTreeMap<String, Value> = BTreeMap::new();
    for host in &sorted_hosts {
        let valid_snaps = &valid_by_host[host];
        let valid_id_set: BTreeSet<String> = valid_snaps
            .iter()
            .map(|s| s["id"].as_str().unwrap().to_string())
            .collect();
        let mut chain_breaks: Vec<Value> = vec![];
        for s in valid_snaps {
            if s["kind"].as_str() != Some("incremental") {
                continue;
            }
            let pid = s.get("parent_id").and_then(Value::as_str).unwrap_or("");
            if !valid_id_set.contains(pid) {
                let id = s["id"].as_str().unwrap().to_string();
                let status = if chain_break_ids.contains(&id) {
                    "explained_break"
                } else {
                    "unexpected_break"
                };
                let mut m = Map::new();
                m.insert("id".to_string(), Value::String(id));
                m.insert("parent_id".to_string(), Value::String(pid.to_string()));
                m.insert("status".to_string(), Value::String(status.to_string()));
                chain_breaks.push(Value::Object(m));
            }
        }
        chain_breaks.sort_by(|a, b| {
            a["id"].as_str().unwrap().cmp(b["id"].as_str().unwrap())
        });
        let mut compromised: Vec<String> = valid_snaps
            .iter()
            .filter(|s| tamper_ids.contains(s["id"].as_str().unwrap()))
            .map(|s| s["id"].as_str().unwrap().to_string())
            .collect();
        compromised.sort();
        let mut entry = Map::new();
        entry.insert("host".to_string(), Value::String(host.clone()));
        entry.insert("chain_breaks".to_string(), Value::Array(chain_breaks));
        entry.insert(
            "compromised".to_string(),
            Value::Array(compromised.into_iter().map(Value::String).collect()),
        );
        integrity_per_host.insert(host.clone(), Value::Object(entry));
    }

    let priority_key = |sid: &str| -> (i64, i64, i64, String) {
        let (host, s) = &snap_global_index[sid];
        let tier = profile_by_host[host]["tier"].as_str().unwrap();
        let td = s.get("taken_day").and_then(Value::as_i64).unwrap();
        let sz = s.get("size_mb").and_then(Value::as_i64).unwrap();
        (tier_rank(tier), td, -sz, sid.to_string())
    };

    let initial_kept_size: i64 = retention_kept_ids
        .iter()
        .map(|sid| {
            snap_global_index[sid]
                .1
                .get("size_mb")
                .and_then(Value::as_i64)
                .unwrap()
        })
        .sum();

    let mut capacity_evicted_records: Vec<Value> = vec![];
    let mut running = initial_kept_size;

    let mut non_exempt_kept: BTreeSet<String> = BTreeSet::new();
    let mut tier_totals: BTreeMap<String, i64> = BTreeMap::new();
    for sid in &retention_kept_ids {
        let (host, s) = &snap_global_index[sid];
        if profile_by_host[host]
            .get("exempt")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            continue;
        }
        non_exempt_kept.insert(sid.clone());
        let tier = profile_by_host[host]["tier"].as_str().unwrap().to_string();
        let sz = s.get("size_mb").and_then(Value::as_i64).unwrap();
        *tier_totals.entry(tier).or_insert(0) += sz;
    }

    let mut capacity_evicted_ids: BTreeSet<String> = BTreeSet::new();

    let tier_pass_order: [&str; 3] = ["bronze", "gold", "silver"];
    for tier_name in &tier_pass_order {
        let quota = *tier_quotas.get(*tier_name).unwrap_or(&0);
        let mut eligible: Vec<String> = non_exempt_kept
            .iter()
            .filter(|sid| !capacity_evicted_ids.contains(*sid))
            .filter(|sid| {
                let (host, _) = &snap_global_index[*sid];
                profile_by_host[host]["tier"].as_str().unwrap() == *tier_name
            })
            .cloned()
            .collect();
        eligible.sort_by(|a, b| priority_key(a).cmp(&priority_key(b)));
        let mut idx = 0usize;
        while *tier_totals.get(*tier_name).unwrap_or(&0) > quota && idx < eligible.len() {
            let sid = &eligible[idx];
            let (host, s) = &snap_global_index[sid];
            let sz = s.get("size_mb").and_then(Value::as_i64).unwrap();
            running -= sz;
            *tier_totals.get_mut(*tier_name).unwrap() -= sz;
            capacity_evicted_ids.insert(sid.clone());
            let mut rec = Map::new();
            rec.insert("id".to_string(), Value::String(sid.clone()));
            rec.insert("host".to_string(), Value::String(host.clone()));
            rec.insert("pass".to_string(), Value::String("tier_quota".to_string()));
            rec.insert("size_mb".to_string(), Value::Number(Number::from(sz)));
            rec.insert(
                "running_size_mb".to_string(),
                Value::Number(Number::from(running)),
            );
            capacity_evicted_records.push(Value::Object(rec));
            idx += 1;
        }
    }

    if running > capacity_mb {
        let mut eligible: Vec<String> = non_exempt_kept
            .iter()
            .filter(|sid| !capacity_evicted_ids.contains(*sid))
            .cloned()
            .collect();
        eligible.sort_by(|a, b| priority_key(a).cmp(&priority_key(b)));
        let mut idx = 0usize;
        while running > capacity_mb && idx < eligible.len() {
            let sid = &eligible[idx];
            let (host, s) = &snap_global_index[sid];
            let sz = s.get("size_mb").and_then(Value::as_i64).unwrap();
            running -= sz;
            capacity_evicted_ids.insert(sid.clone());
            let mut rec = Map::new();
            rec.insert("id".to_string(), Value::String(sid.clone()));
            rec.insert("host".to_string(), Value::String(host.clone()));
            rec.insert(
                "pass".to_string(),
                Value::String("global_capacity".to_string()),
            );
            rec.insert("size_mb".to_string(), Value::Number(Number::from(sz)));
            rec.insert(
                "running_size_mb".to_string(),
                Value::Number(Number::from(running)),
            );
            capacity_evicted_records.push(Value::Object(rec));
            idx += 1;
        }
    }

    let eviction_plan_final_size: i64 = retention_kept_ids
        .iter()
        .filter(|sid| !capacity_evicted_ids.contains(*sid))
        .map(|sid| {
            snap_global_index[sid]
                .1
                .get("size_mb")
                .and_then(Value::as_i64)
                .unwrap()
        })
        .sum();

    let mut cascade_evicted_ids: BTreeSet<String> = BTreeSet::new();
    for host in &sorted_hosts {
        let host_snaps = &valid_by_host[host];
        let snap_by_id_h: BTreeMap<String, &Value> = host_snaps
            .iter()
            .map(|s| (s["id"].as_str().unwrap().to_string(), s))
            .collect();
        for s in host_snaps {
            let sid = s["id"].as_str().unwrap().to_string();
            if !retention_kept_ids.contains(&sid) {
                continue;
            }
            if capacity_evicted_ids.contains(&sid) {
                continue;
            }
            if s["kind"].as_str() != Some("incremental") {
                continue;
            }
            let mut cur: &Value = s;
            let mut visited: BTreeSet<String> = BTreeSet::new();
            loop {
                let pid = match cur.get("parent_id").and_then(Value::as_str) {
                    Some(p) if !p.is_empty() => p.to_string(),
                    _ => break,
                };
                if !visited.insert(pid.clone()) {
                    break;
                }
                let parent = match snap_by_id_h.get(&pid) {
                    Some(p) => *p,
                    None => break,
                };
                if capacity_evicted_ids.contains(parent["id"].as_str().unwrap()) {
                    cascade_evicted_ids.insert(sid.clone());
                    break;
                }
                if parent["kind"].as_str() != Some("incremental") {
                    break;
                }
                cur = parent;
            }
        }
    }

    let final_kept_ids: BTreeSet<String> = retention_kept_ids
        .iter()
        .filter(|sid| !capacity_evicted_ids.contains(*sid))
        .filter(|sid| !cascade_evicted_ids.contains(*sid))
        .cloned()
        .collect();

    let mut retention_entries: Vec<Value> = vec![];
    let mut containment_entries: Vec<Value> = vec![];

    for host in &sorted_hosts {
        let mut sorted_snaps: Vec<&Value> = valid_by_host[host].iter().collect();
        sorted_snaps.sort_by(|a, b| {
            a["id"].as_str().unwrap().cmp(b["id"].as_str().unwrap())
        });
        for s in sorted_snaps {
            let sid = s["id"].as_str().unwrap().to_string();
            let sz = s.get("size_mb").and_then(Value::as_i64).unwrap();
            let decision: &str;
            let reason: &str;
            let matched_rule: Value;
            if contained_ids.contains(&sid) {
                decision = "evict";
                reason = "tamper_containment";
                matched_rule = Value::Null;
                let mut m = Map::new();
                m.insert("id".to_string(), Value::String(sid.clone()));
                m.insert("host".to_string(), Value::String(host.clone()));
                m.insert("size_mb".to_string(), Value::Number(Number::from(sz)));
                containment_entries.push(Value::Object(m));
            } else if final_kept_ids.contains(&sid) {
                decision = "keep";
                let mr = matched_rule_for
                    .get(&sid)
                    .cloned()
                    .unwrap_or_default();
                if mr == "exempt" {
                    reason = "exempt";
                } else {
                    reason = "retained_by_rule";
                }
                matched_rule = Value::String(mr);
            } else if capacity_evicted_ids.contains(&sid) {
                decision = "evict";
                reason = "capacity_overflow";
                matched_rule = Value::Null;
            } else if cascade_evicted_ids.contains(&sid) {
                decision = "evict";
                reason = "cascade_overflow";
                matched_rule = Value::Null;
            } else {
                decision = "evict";
                reason = "no_matching_rule";
                matched_rule = Value::Null;
            }
            let mut m = Map::new();
            m.insert("id".to_string(), Value::String(sid));
            m.insert("host".to_string(), Value::String(host.clone()));
            m.insert("decision".to_string(), Value::String(decision.to_string()));
            m.insert("reason".to_string(), Value::String(reason.to_string()));
            m.insert("matched_rule".to_string(), matched_rule);
            retention_entries.push(Value::Object(m));
        }
    }

    retention_entries.sort_by(|a, b| {
        let ha = a["host"].as_str().unwrap();
        let hb = b["host"].as_str().unwrap();
        match ha.cmp(hb) {
            std::cmp::Ordering::Equal => a["id"].as_str().unwrap().cmp(b["id"].as_str().unwrap()),
            o => o,
        }
    });
    containment_entries.sort_by(|a, b| {
        let ha = a["host"].as_str().unwrap();
        let hb = b["host"].as_str().unwrap();
        match ha.cmp(hb) {
            std::cmp::Ordering::Equal => a["id"].as_str().unwrap().cmp(b["id"].as_str().unwrap()),
            o => o,
        }
    });

    let total_size_contained_mb: i64 = containment_entries
        .iter()
        .map(|e| e["size_mb"].as_i64().unwrap())
        .sum();

    let mut host_summary_list: Vec<Value> = vec![];
    for host in &sorted_hosts {
        let valid_snaps = &valid_by_host[host];
        let kept_for_host: Vec<&Value> = valid_snaps
            .iter()
            .filter(|s| final_kept_ids.contains(s["id"].as_str().unwrap()))
            .collect();
        let kept_count = kept_for_host.len() as i64;
        let kept_size: i64 = kept_for_host
            .iter()
            .map(|s| s.get("size_mb").and_then(Value::as_i64).unwrap())
            .sum();
        let evicted_count = valid_snaps.len() as i64 - kept_count;
        let oldest_kept_day: Value = if kept_count == 0 {
            Value::Null
        } else {
            let min_day = kept_for_host
                .iter()
                .map(|s| s.get("taken_day").and_then(Value::as_i64).unwrap())
                .min()
                .unwrap();
            Value::Number(Number::from(min_day))
        };
        let ig = &integrity_per_host[host];
        let cb_len = ig["chain_breaks"].as_array().unwrap().len();
        let cm_len = ig["compromised"].as_array().unwrap().len();
        let integrity_status = if cm_len > 0 {
            "compromised"
        } else if cb_len > 0 {
            "chain_issues"
        } else {
            "ok"
        };
        let profile = &profile_by_host[host];
        let tier = profile["tier"].as_str().unwrap();
        let exempt = profile.get("exempt").and_then(Value::as_bool).unwrap_or(false);
        let mut m = Map::new();
        m.insert("host".to_string(), Value::String(host.clone()));
        m.insert("tier".to_string(), Value::String(tier.to_string()));
        m.insert("exempt".to_string(), Value::Bool(exempt));
        m.insert(
            "valid_snapshots".to_string(),
            Value::Number(Number::from(valid_snaps.len() as i64)),
        );
        m.insert(
            "kept_count".to_string(),
            Value::Number(Number::from(kept_count)),
        );
        m.insert(
            "evicted_count".to_string(),
            Value::Number(Number::from(evicted_count)),
        );
        m.insert(
            "kept_size_mb".to_string(),
            Value::Number(Number::from(kept_size)),
        );
        m.insert("oldest_kept_day".to_string(), oldest_kept_day);
        m.insert(
            "integrity_status".to_string(),
            Value::String(integrity_status.to_string()),
        );
        host_summary_list.push(Value::Object(m));
    }

    let final_kept_size: i64 = final_kept_ids
        .iter()
        .map(|sid| {
            snap_global_index[sid]
                .1
                .get("size_mb")
                .and_then(Value::as_i64)
                .unwrap()
        })
        .sum();
    let total_valid_snapshots: i64 = valid_by_host.values().map(|v| v.len() as i64).sum();
    let total_invalid_snapshots: i64 = invalid_count_by_host.values().sum();

    let mut invalid_per_host = Map::new();
    for (h, c) in &invalid_count_by_host {
        if *c > 0 {
            invalid_per_host.insert(h.clone(), Value::Number(Number::from(*c)));
        }
    }

    let mut summary_doc = Map::new();
    summary_doc.insert(
        "capacity_mb".to_string(),
        Value::Number(Number::from(capacity_mb)),
    );
    summary_doc.insert(
        "current_day".to_string(),
        Value::Number(Number::from(current_day)),
    );
    summary_doc.insert(
        "total_valid_snapshots".to_string(),
        Value::Number(Number::from(total_valid_snapshots)),
    );
    summary_doc.insert(
        "total_invalid_snapshots".to_string(),
        Value::Number(Number::from(total_invalid_snapshots)),
    );
    summary_doc.insert(
        "total_size_before_eviction_mb".to_string(),
        Value::Number(Number::from(initial_kept_size)),
    );
    summary_doc.insert(
        "total_size_after_eviction_mb".to_string(),
        Value::Number(Number::from(final_kept_size)),
    );
    summary_doc.insert(
        "total_size_contained_mb".to_string(),
        Value::Number(Number::from(total_size_contained_mb)),
    );
    summary_doc.insert(
        "ignored_incident_events".to_string(),
        Value::Number(Number::from(ignored_count)),
    );
    summary_doc.insert(
        "invalid_snapshots_per_host".to_string(),
        Value::Object(invalid_per_host),
    );

    let retention_doc = json!({"snapshots": retention_entries});
    let eviction_plan_doc = json!({
        "capacity_mb": capacity_mb,
        "initial_size_mb": initial_kept_size,
        "final_size_mb": eviction_plan_final_size,
        "evictions": capacity_evicted_records,
        "containment_evictions": containment_entries,
    });
    let integrity_doc = json!({
        "hosts": sorted_hosts.iter().map(|h| integrity_per_host[h].clone()).collect::<Vec<_>>(),
    });
    let host_summary_doc = json!({"hosts": host_summary_list});

    write_json(&out.join("retention.json"), &retention_doc);
    write_json(&out.join("eviction_plan.json"), &eviction_plan_doc);
    write_json(&out.join("integrity.json"), &integrity_doc);
    write_json(&out.join("host_summary.json"), &host_summary_doc);
    write_json(&out.join("summary.json"), &Value::Object(summary_doc));
}
AUDITOR_RS_EOF

cd "$AUDITOR_DIR"
cargo build --release --offline --locked

"$AUDITOR_DIR/target/release/auditor"
