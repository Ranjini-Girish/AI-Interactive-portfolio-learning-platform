#!/bin/bash
set -euo pipefail
export PATH="/usr/local/cargo/bin:${PATH:-}"
cd /app
mkdir -p src audit

cat > Cargo.toml <<'EOF'
[package]
name = "tabgap"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1.0.210", features = ["derive"] }
serde_json = "1.0.128"
sha2 = "0.10.8"
EOF

cat > src/main.rs <<'RS'
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

const ROOT: &str = "/app/tab_bundle";
const OUT: &str = "/app/audit";

fn read_tsv(path: &Path) -> (Vec<String>, Vec<Vec<String>>) {
    let raw = match fs::read_to_string(path) {
        Ok(s) => s,
        Err(_) => return (Vec::new(), Vec::new()),
    };
    if raw.is_empty() {
        return (Vec::new(), Vec::new());
    }
    let mut lines: Vec<&str> = raw.split('\n').collect();
    if let Some(last) = lines.last() {
        if last.is_empty() {
            lines.pop();
        }
    }
    if lines.is_empty() {
        return (Vec::new(), Vec::new());
    }
    let header: Vec<String> = lines[0].split('\t').map(|s| s.to_string()).collect();
    let n = header.len();
    let mut rows: Vec<Vec<String>> = Vec::new();
    for ln in &lines[1..] {
        if ln.is_empty() {
            rows.push(vec![String::new(); n]);
            continue;
        }
        let mut parts: Vec<String> = ln.split('\t').map(|s| s.to_string()).collect();
        while parts.len() < n {
            parts.push(String::new());
        }
        rows.push(parts);
    }
    (header, rows)
}

fn is_missing(value: &str, extra: &BTreeSet<String>) -> bool {
    if value.is_empty() {
        return true;
    }
    if value.chars().all(|c| matches!(c, ' ' | '\t' | '\r' | '\n')) {
        return true;
    }
    if value == "NA" {
        return true;
    }
    if extra.contains(value) {
        return true;
    }
    false
}

fn format_pct(count: i64, total: i64) -> String {
    if total <= 0 {
        return "0.000000".to_string();
    }
    let num: i128 = (count as i128) * 100_000_000_i128;
    let q = num / (total as i128);
    let int_part = q / 1_000_000;
    let frac = q - int_part * 1_000_000;
    format!("{}.{:06}", int_part, frac)
}

fn rate_to_micro(s: &str) -> i128 {
    let parts: Vec<&str> = s.split('.').collect();
    let int_part: i128 = parts[0].parse().unwrap_or(0);
    let frac_part: i128 = parts.get(1).and_then(|s| s.parse().ok()).unwrap_or(0);
    int_part * 1_000_000 + frac_part
}

fn write_json(path: &Path, v: &Value) {
    let mut s = serde_json::to_string_pretty(v).expect("serialize");
    s.push('\n');
    fs::write(path, s).expect("write");
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

fn main() {
    let root = Path::new(ROOT);
    let catalog: Value = serde_json::from_str(
        &fs::read_to_string(root.join("catalog.json")).expect("read catalog"),
    )
    .expect("parse catalog");
    let policy: Value = serde_json::from_str(
        &fs::read_to_string(root.join("policy.json")).expect("read policy"),
    )
    .expect("parse policy");

    let extra: BTreeSet<String> = policy["extra_missing_tokens"]
        .as_array()
        .map(|a| a.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
        .unwrap_or_default();
    let skip: BTreeSet<String> = policy["rollup_skip_columns"]
        .as_array()
        .map(|a| a.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
        .unwrap_or_default();
    let mut dedup_keys: Vec<String> = policy["dedup_keys"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();
    dedup_keys.sort();
    let mut global_keys: Vec<String> = policy["global_keys"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();
    global_keys.sort();

    let inputs: Vec<&Value> = catalog["inputs"]
        .as_array()
        .map(|a| a.iter().collect())
        .unwrap_or_default();

    let mut tables: Vec<(String, Vec<String>, Vec<Vec<String>>, Vec<String>)> = Vec::new();
    let mut union_kept: BTreeSet<String> = BTreeSet::new();

    for entry in &inputs {
        let did = entry["dataset_id"].as_str().unwrap_or("").to_string();
        let rel = entry["relative_path"].as_str().unwrap_or("").to_string();
        let (header, rows) = read_tsv(&root.join(&rel));
        let kept: Vec<String> = header.iter().filter(|c| !skip.contains(*c)).cloned().collect();
        for c in &kept {
            union_kept.insert(c.clone());
        }
        tables.push((did, header, rows, kept));
    }

    let global_kept: Vec<String> = union_kept.iter().cloned().collect();

    let mut presence_rows: Vec<(String, i64, String)> = Vec::new();
    let mut col_missing: BTreeMap<String, i64> = BTreeMap::new();
    for c in &global_kept {
        col_missing.insert(c.clone(), 0);
    }
    let mut dataset_rollups_raw: Vec<(String, i64, i64, i64, Vec<String>)> = Vec::new();
    let mut duplicate_events: Vec<(String, Vec<String>, i64, i64)> = Vec::new();
    let mut global_events: Vec<(Vec<String>, String, i64, String, i64)> = Vec::new();
    let mut global_first: BTreeMap<Vec<String>, (String, i64)> = BTreeMap::new();

    let mut total_data_rows: i64 = 0;
    let mut global_index: i64 = 0;

    for (did, header, rows, kept) in &tables {
        let kept_set: BTreeSet<String> = kept.iter().cloned().collect();
        let mut col_idx: BTreeMap<String, usize> = BTreeMap::new();
        for (i, h) in header.iter().enumerate() {
            col_idx.insert(h.clone(), i);
        }
        let dup_enabled = dedup_keys.iter().all(|k| kept_set.contains(k));
        let mut dataset_first: BTreeMap<Vec<String>, i64> = BTreeMap::new();
        let mut ds_missing: i64 = 0;

        for (zero_idx, row) in rows.iter().enumerate() {
            let ri = (zero_idx + 1) as i64;
            global_index += 1;
            total_data_rows += 1;

            let mut mask = String::new();
            for c in &global_kept {
                if kept_set.contains(c) {
                    let j = *col_idx.get(c).expect("kept column missing from header index");
                    let cell = if j < row.len() { row[j].as_str() } else { "" };
                    if is_missing(cell, &extra) {
                        mask.push('0');
                        *col_missing.get_mut(c).unwrap() += 1;
                        ds_missing += 1;
                    } else {
                        mask.push('1');
                    }
                } else {
                    mask.push('0');
                    *col_missing.get_mut(c).unwrap() += 1;
                    ds_missing += 1;
                }
            }
            presence_rows.push((did.clone(), ri, mask));

            if dup_enabled {
                let mut dk_values: Vec<String> = Vec::new();
                let mut any_missing = false;
                for k in &dedup_keys {
                    let j = *col_idx.get(k).unwrap();
                    let cell = if j < row.len() { row[j].as_str() } else { "" };
                    if is_missing(cell, &extra) {
                        any_missing = true;
                        break;
                    }
                    dk_values.push(cell.to_string());
                }
                if !any_missing {
                    if let Some(&first_idx) = dataset_first.get(&dk_values) {
                        duplicate_events.push((did.clone(), dk_values.clone(), first_idx, ri));
                    } else {
                        dataset_first.insert(dk_values, ri);
                    }
                }
            }

            let mut gk_values: Vec<String> = Vec::new();
            let mut gk_missing = false;
            for k in &global_keys {
                if !kept_set.contains(k) {
                    gk_missing = true;
                    break;
                }
                let j = *col_idx.get(k).unwrap();
                let cell = if j < row.len() { row[j].as_str() } else { "" };
                if is_missing(cell, &extra) {
                    gk_missing = true;
                    break;
                }
                gk_values.push(cell.to_string());
            }
            if !gk_missing {
                if let Some((first_did, first_gi)) = global_first.get(&gk_values).cloned() {
                    global_events.push((
                        gk_values.clone(),
                        first_did,
                        first_gi,
                        did.clone(),
                        global_index,
                    ));
                } else {
                    global_first.insert(gk_values, (did.clone(), global_index));
                }
            }
        }

        let cells_total = (rows.len() as i64) * (global_kept.len() as i64);
        let mut kc_present = kept.clone();
        kc_present.sort();
        dataset_rollups_raw.push((did.clone(), rows.len() as i64, cells_total, ds_missing, kc_present));
    }

    presence_rows.sort_by(|a, b| (a.0.as_str(), a.1).cmp(&(b.0.as_str(), b.1)));

    duplicate_events.sort_by(|a, b| {
        (&a.0, &a.1, a.3, a.2).cmp(&(&b.0, &b.1, b.3, b.2))
    });

    global_events.sort_by(|a, b| (&a.0, a.4, a.2).cmp(&(&b.0, b.4, b.2)));

    let mut col_rollup_arr: Vec<(String, i64, i64, String, String)> = Vec::new();
    for c in &global_kept {
        let m = *col_missing.get(c).unwrap();
        let p = total_data_rows - m;
        let (mr, pr);
        if total_data_rows <= 0 {
            mr = "0.000000".to_string();
            pr = "0.000000".to_string();
        } else if m == total_data_rows {
            mr = "100.000000".to_string();
            pr = "0.000000".to_string();
        } else if p == total_data_rows {
            mr = "0.000000".to_string();
            pr = "100.000000".to_string();
        } else {
            mr = format_pct(m, total_data_rows);
            pr = format_pct(p, total_data_rows);
        }
        col_rollup_arr.push((c.clone(), m, p, mr, pr));
    }
    col_rollup_arr.sort_by(|a, b| {
        let ra = rate_to_micro(&a.3);
        let rb = rate_to_micro(&b.3);
        rb.cmp(&ra).then(b.1.cmp(&a.1)).then(a.0.cmp(&b.0))
    });

    let mut ds_rollup_arr: Vec<(String, i64, i64, i64, Vec<String>, String)> = Vec::new();
    for (did, dr, ct, dm, kcp) in &dataset_rollups_raw {
        let mr;
        if *ct <= 0 {
            mr = "0.000000".to_string();
        } else if *dm == *ct {
            mr = "100.000000".to_string();
        } else if *dm == 0 {
            mr = "0.000000".to_string();
        } else {
            mr = format_pct(*dm, *ct);
        }
        ds_rollup_arr.push((did.clone(), *dr, *ct, *dm, kcp.clone(), mr));
    }
    ds_rollup_arr.sort_by(|a, b| {
        let ra = rate_to_micro(&a.5);
        let rb = rate_to_micro(&b.5);
        rb.cmp(&ra).then(b.1.cmp(&a.1)).then(a.0.cmp(&b.0))
    });

    let mut col_arr: Vec<Value> = Vec::new();
    for (n, m, p, mr, pr) in &col_rollup_arr {
        let mut o = Map::new();
        o.insert("column_name".into(), Value::String(n.clone()));
        o.insert("missing_count".into(), json!(*m));
        o.insert("missing_rate".into(), Value::String(mr.clone()));
        o.insert("present_count".into(), json!(*p));
        o.insert("present_rate".into(), Value::String(pr.clone()));
        o.insert("total_rows".into(), json!(total_data_rows));
        col_arr.push(Value::Object(o));
    }

    let mut ds_arr: Vec<Value> = Vec::new();
    for (did, dr, ct, dm, kcp, mr) in &ds_rollup_arr {
        let mut o = Map::new();
        o.insert("cells_total".into(), json!(*ct));
        o.insert("data_rows".into(), json!(*dr));
        o.insert("dataset_id".into(), Value::String(did.clone()));
        o.insert(
            "kept_columns_present".into(),
            Value::Array(kcp.iter().map(|s| Value::String(s.clone())).collect()),
        );
        o.insert("missing_count".into(), json!(*dm));
        o.insert("missing_rate_dataset".into(), Value::String(mr.clone()));
        ds_arr.push(Value::Object(o));
    }

    let mut pr_arr: Vec<Value> = Vec::new();
    for (did, ri, mask) in &presence_rows {
        let mut o = Map::new();
        o.insert("dataset_id".into(), Value::String(did.clone()));
        o.insert("mask".into(), Value::String(mask.clone()));
        o.insert("row_index".into(), json!(*ri));
        pr_arr.push(Value::Object(o));
    }

    let mut dup_arr: Vec<Value> = Vec::new();
    for (did, kv, fi, li) in &duplicate_events {
        let mut o = Map::new();
        o.insert("dataset_id".into(), Value::String(did.clone()));
        o.insert("first_row_index".into(), json!(*fi));
        o.insert(
            "key_value".into(),
            Value::Array(kv.iter().map(|s| Value::String(s.clone())).collect()),
        );
        o.insert("later_row_index".into(), json!(*li));
        dup_arr.push(Value::Object(o));
    }

    let mut ge_arr: Vec<Value> = Vec::new();
    for (kv, fdid, fgi, ldid, lgi) in &global_events {
        let mut o = Map::new();
        o.insert("first_dataset_id".into(), Value::String(fdid.clone()));
        o.insert("first_global_index".into(), json!(*fgi));
        o.insert(
            "key_value".into(),
            Value::Array(kv.iter().map(|s| Value::String(s.clone())).collect()),
        );
        o.insert("later_dataset_id".into(), Value::String(ldid.clone()));
        o.insert("later_global_index".into(), json!(*lgi));
        ge_arr.push(Value::Object(o));
    }

    let catalog_bytes = fs::read(root.join("catalog.json")).expect("read catalog bytes");
    let catalog_sha = sha256_hex(&catalog_bytes);

    let mut meta = Map::new();
    meta.insert("catalog_sha256".into(), Value::String(catalog_sha));
    meta.insert(
        "dedup_keys".into(),
        Value::Array(dedup_keys.iter().map(|s| Value::String(s.clone())).collect()),
    );
    meta.insert(
        "extra_missing_tokens".into(),
        Value::Array(extra.iter().map(|s| Value::String(s.clone())).collect()),
    );
    meta.insert(
        "global_keys".into(),
        Value::Array(global_keys.iter().map(|s| Value::String(s.clone())).collect()),
    );
    meta.insert(
        "rollup_skip_columns".into(),
        Value::Array(skip.iter().map(|s| Value::String(s.clone())).collect()),
    );

    let mut summary = Map::new();
    summary.insert("catalog_inputs".into(), json!(inputs.len() as i64));
    summary.insert("duplicate_key_events".into(), json!(duplicate_events.len() as i64));
    summary.insert("global_key_events".into(), json!(global_events.len() as i64));
    summary.insert("kept_column_count".into(), json!(global_kept.len() as i64));
    summary.insert("total_data_rows".into(), json!(total_data_rows));

    let mut report = Map::new();
    report.insert("column_rollups".into(), Value::Array(col_arr));
    report.insert("dataset_rollups".into(), Value::Array(ds_arr));
    report.insert("duplicate_key_events".into(), Value::Array(dup_arr));
    report.insert("global_key_events".into(), Value::Array(ge_arr));
    report.insert("meta".into(), Value::Object(meta));
    report.insert("presence_rows".into(), Value::Array(pr_arr));
    report.insert("summary".into(), Value::Object(summary));

    fs::create_dir_all(OUT).expect("mkdir audit");
    write_json(&Path::new(OUT).join("gap_report.json"), &Value::Object(report));
}
RS

cargo build --release
find /app/audit -mindepth 1 -maxdepth 1 -delete 2>/dev/null || true
mkdir -p /app/audit
./target/release/tabgap
