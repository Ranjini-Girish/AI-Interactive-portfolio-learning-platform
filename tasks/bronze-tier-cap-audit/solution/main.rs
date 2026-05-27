use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::env;
use std::fs;
use std::path::PathBuf;

#[derive(Deserialize)]
struct Policy {
    audit_day: i64,
    tier_order: Vec<String>,
    tier_caps: HashMap<String, i64>,
}

#[derive(Deserialize)]
struct Derate {
    tier: String,
    factor_bp: i64,
    start_day: i64,
    end_day: i64,
}

#[derive(Deserialize)]
struct Freeze {
    item_id: String,
    start_day: i64,
    end_day: i64,
}

#[derive(Deserialize)]
struct Events {
    #[serde(default)]
    tier_derates: Vec<Derate>,
    #[serde(default)]
    item_freezes: Vec<Freeze>,
}

#[derive(Deserialize)]
struct Item {
    item_id: String,
    tier: String,
    demand: i64,
}

fn tier_rank(tier: &str, order: &[String]) -> usize {
    order.iter().position(|t| t == tier).unwrap_or(order.len())
}

fn write_json(path: &PathBuf, value: &Value) -> std::io::Result<()> {
    let mut buf = serde_json::to_string_pretty(value)?;
    buf.push('\n');
    fs::write(path, buf)
}

fn main() {
    let data = PathBuf::from(env::var("QUOTA_DATA_DIR").unwrap_or_else(|_| "/app/quota_lab".into()));
    let audit = PathBuf::from(env::var("QUOTA_AUDIT_DIR").unwrap_or_else(|_| "/app/audit".into()));
    fs::create_dir_all(&audit).unwrap();

    let policy: Policy = serde_json::from_str(&fs::read_to_string(data.join("policy.json")).unwrap()).unwrap();
    let events: Events = serde_json::from_str(&fs::read_to_string(data.join("events.json")).unwrap()).unwrap();

    let mut caps = policy.tier_caps.clone();
    for d in &events.tier_derates {
        if d.start_day <= policy.audit_day && policy.audit_day <= d.end_day {
            if let Some(c) = caps.get_mut(&d.tier) {
                *c = *c * d.factor_bp / 10000;
            }
        }
    }
    let mut frozen = HashSet::new();
    for f in &events.item_freezes {
        if f.start_day <= policy.audit_day && policy.audit_day <= f.end_day {
            frozen.insert(f.item_id.clone());
        }
    }

    let mut items: Vec<Item> = Vec::new();
    for entry in fs::read_dir(data.join("items")).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().and_then(|s| s.to_str()) == Some("json") {
            items.push(serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap());
        }
    }
    items.sort_by(|a, b| {
        tier_rank(&a.tier, &policy.tier_order)
            .cmp(&tier_rank(&b.tier, &policy.tier_order))
            .then_with(|| a.tier.cmp(&b.tier))
            .then_with(|| a.item_id.cmp(&b.item_id))
    });

    let mut tier_rem = caps.clone();
    let mut rows: Vec<Value> = Vec::new();
    let mut sc = BTreeMap::from([("frozen", 0), ("ok", 0), ("shortfall", 0)]);

    for it in items {
        if frozen.contains(&it.item_id) {
            rows.push(json!({
                "item_id": it.item_id,
                "tier": it.tier,
                "status": "frozen",
                "demand": it.demand,
                "allocated": 0
            }));
            *sc.get_mut("frozen").unwrap() += 1;
            continue;
        }
        let left = *tier_rem.get(&it.tier).unwrap_or(&0);
        let alloc = std::cmp::min(it.demand, left);
        tier_rem.insert(it.tier.clone(), left - alloc);
        let st = if alloc == it.demand { "ok" } else { "shortfall" };
        *sc.get_mut(st).unwrap() += 1;
        rows.push(json!({
            "item_id": it.item_id,
            "tier": it.tier,
            "status": st,
            "demand": it.demand,
            "allocated": alloc
        }));
    }

    let mut touched: Vec<String> = Vec::new();
    for r in &rows {
        if r["allocated"].as_i64().unwrap_or(0) > 0 {
            let t = r["tier"].as_str().unwrap().to_string();
            if !touched.contains(&t) {
                touched.push(t);
            }
        }
    }
    touched.sort_unstable();

    let summary = json!({
        "audit_day": policy.audit_day,
        "items_processed": rows.len(),
        "frozen_items": sc["frozen"],
        "status_counts": sc,
        "tiers_touched": touched,
    });
    write_json(&audit.join("allocations.json"), &json!({ "items": rows })).unwrap();
    write_json(&audit.join("summary.json"), &summary).unwrap();
}
