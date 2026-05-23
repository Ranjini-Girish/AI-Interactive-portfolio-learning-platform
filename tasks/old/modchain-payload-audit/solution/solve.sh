#!/bin/bash
set -euo pipefail
export PATH="/usr/local/cargo/bin:${PATH:-}"
cd /app
mkdir -p src audit

cat > Cargo.toml <<'EOF'
[package]
name = "modchain"
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

const ROOT: &str = "/app/mod_chain_lab";
const OUT: &str = "/app/audit/mod_digest.json";

fn sha256_file(path: &Path) -> String {
    let bytes = fs::read(path).unwrap_or_default();
    let mut h = Sha256::new();
    h.update(&bytes);
    format!("{:x}", h.finalize())
}

fn read_json(path: &Path) -> Value {
    let s = fs::read_to_string(path).expect("read json");
    serde_json::from_str(&s).expect("parse json")
}

fn as_i64(v: &Value) -> i64 {
    v.as_i64().unwrap_or_else(|| v.as_f64().unwrap_or(0.0) as i64)
}

fn mod_pos(x: i64, m: i64) -> i64 {
    let mut r = x % m;
    if r < 0 {
        r += m;
    }
    r
}

fn parse_hex(payload: &str) -> (Vec<u8>, bool) {
    if payload.len() % 2 != 0 {
        return (Vec::new(), false);
    }
    let mut out: Vec<u8> = Vec::new();
    let mut i = 0;
    while i < payload.len() {
        let pair = &payload[i..i + 2];
        for ch in pair.chars() {
            if !matches!(ch, '0'..='9' | 'a'..='f') {
                return (Vec::new(), false);
            }
        }
        out.push(u8::from_str_radix(pair, 16).unwrap());
        i += 2;
    }
    (out, true)
}

fn sort_keys(v: Value) -> Value {
    match v {
        Value::Object(map) => {
            let mut keys: Vec<String> = map.keys().cloned().collect();
            keys.sort();
            let mut old = map;
            let mut out = Map::new();
            for k in keys {
                let val = old.remove(&k).unwrap();
                out.insert(k, sort_keys(val));
            }
            Value::Object(out)
        }
        Value::Array(arr) => Value::Array(arr.into_iter().map(sort_keys).collect()),
        other => other,
    }
}

fn write_json(path: &Path, v: &Value) {
    let mut s = serde_json::to_string_pretty(v).expect("serialize");
    s.push('\n');
    fs::write(path, s).expect("write");
}

fn main() {
    let root = Path::new(ROOT);
    let policy = read_json(&root.join("policy.json"));
    let catalog = read_json(&root.join("catalog.json"));
    let incidents = read_json(&root.join("incidents.json"));
    let pool = read_json(&root.join("pool_state.json"));

    let m = as_i64(&policy["modulus"]);
    let b = mod_pos(as_i64(&policy["base"]), m);
    let h0 = mod_pos(as_i64(&policy["init"]), m);
    let dday = as_i64(&policy["current_day"]);

    let mut tier_bias: BTreeMap<String, i64> = BTreeMap::new();
    if let Some(obj) = policy["tier_bias"].as_object() {
        for (k, v) in obj {
            tier_bias.insert(k.clone(), as_i64(v));
        }
    }

    let cap: Option<i64> = match &pool["terminal_sum_cap"] {
        Value::Null => None,
        v => Some(as_i64(v)),
    };

    let mut suppressed: BTreeSet<String> = BTreeSet::new();
    let mut bias_addends: BTreeMap<String, i64> = BTreeMap::new();
    let mut compromised: BTreeSet<String> = BTreeSet::new();

    if let Some(arr) = incidents["events"].as_array() {
        for ev in arr {
            let kind = ev["kind"].as_str().unwrap_or("");
            if kind == "suppress_frame" {
                let sd = as_i64(&ev["start_day"]);
                let ed = as_i64(&ev["end_day"]);
                if sd <= dday && dday <= ed {
                    suppressed.insert(ev["frame_id"].as_str().unwrap_or("").to_string());
                }
            } else if kind == "bias_window" {
                let sd = as_i64(&ev["start_day"]);
                let ed = as_i64(&ev["end_day"]);
                if sd <= dday && dday <= ed {
                    let sid = ev["stream_id"].as_str().unwrap_or("").to_string();
                    let add = as_i64(&ev["addend"]);
                    *bias_addends.entry(sid).or_insert(0) += add;
                }
            } else if kind == "compromise_stream" {
                let acc = ev["accepted"].as_bool().unwrap_or(false);
                let day = as_i64(&ev["day"]);
                if acc && dday >= day {
                    compromised.insert(ev["stream_id"].as_str().unwrap_or("").to_string());
                }
            }
        }
    }

    let mut stream_rollups: Vec<Map<String, Value>> = Vec::new();
    let mut raw_by_stream: BTreeMap<String, i64> = BTreeMap::new();

    let mut total_cataloged: i64 = 0;
    let mut total_after_suppress: i64 = 0;

    let streams = catalog["streams"].as_array().expect("streams");
    for stream in streams {
        let sid = stream["stream_id"].as_str().unwrap_or("").to_string();
        let paths = stream["frame_paths"].as_array().expect("frame_paths");
        total_cataloged += paths.len() as i64;

        let mut frames: Vec<Value> = Vec::new();
        for p in paths {
            let rel = p.as_str().expect("path");
            let fp = root.join(rel);
            frames.push(read_json(&fp));
        }

        let mut kept: Vec<Value> = Vec::new();
        for fr in frames {
            let fid = fr["frame_id"].as_str().unwrap_or("");
            if suppressed.contains(fid) {
                continue;
            }
            kept.push(fr);
        }
        total_after_suppress += kept.len() as i64;

        let mut diags: BTreeSet<String> = BTreeSet::new();

        if compromised.contains(&sid) {
            diags.insert("stream_compromised".to_string());
            let mut row = Map::new();
            row.insert("diagnostics".to_string(), json!(diags.iter().cloned().collect::<Vec<_>>()));
            row.insert("frames_considered".to_string(), json!(kept.len() as i64));
            row.insert("mix_steps".to_string(), json!(0));
            row.insert("status".to_string(), json!("quarantined"));
            row.insert("stream_id".to_string(), json!(sid.clone()));
            row.insert("terminal_residue".to_string(), json!(0));
            stream_rollups.push(row);
            raw_by_stream.insert(sid.clone(), 0);
            continue;
        }

        kept.sort_by(|a, b| {
            let sa = a["seq"].as_i64().unwrap_or_else(|| a["seq"].as_f64().unwrap_or(0.0) as i64);
            let sb = b["seq"].as_i64().unwrap_or_else(|| b["seq"].as_f64().unwrap_or(0.0) as i64);
            let fa = a["frame_id"].as_str().unwrap_or("");
            let fb = b["frame_id"].as_str().unwrap_or("");
            sa.cmp(&sb).then_with(|| fa.cmp(fb))
        });

        let add = mod_pos(*bias_addends.get(&sid).unwrap_or(&0), m);
        let mut h = h0;
        for fr in &kept {
            let payload = fr["payload_hex"].as_str().unwrap_or("");
            let seq = fr["seq"].as_i64().unwrap_or_else(|| fr["seq"].as_f64().unwrap_or(0.0) as i64);
            let tier = fr["tier"].as_str().unwrap_or("");
            let q = mod_pos(seq, m);

            let (bs, ok) = parse_hex(payload);
            if !ok {
                diags.insert("bad_hex".to_string());
            }
            let ssum: i64 = bs.iter().map(|&x| x as i64).sum();
            let ln = bs.len() as i64;

            let tbv = if let Some(tv) = tier_bias.get(tier) {
                *tv
            } else {
                diags.insert("unknown_tier".to_string());
                0
            };

            let mut dig = mod_pos(ssum + ln + q + tbv, m);
            dig = mod_pos(dig + add, m);
            h = mod_pos(h * b + dig, m);
        }

        let mut row = Map::new();
        row.insert(
            "diagnostics".to_string(),
            json!(diags.iter().cloned().collect::<Vec<_>>()),
        );
        row.insert("frames_considered".to_string(), json!(kept.len() as i64));
        row.insert("mix_steps".to_string(), json!(kept.len() as i64));
        row.insert("status".to_string(), json!("ok"));
        row.insert("stream_id".to_string(), json!(sid.clone()));
        row.insert("terminal_residue".to_string(), json!(h));
        stream_rollups.push(row);
        raw_by_stream.insert(sid.clone(), h);
    }

    stream_rollups.sort_by(|a, b| {
        let sa = a["stream_id"].as_str().unwrap_or("");
        let sb = b["stream_id"].as_str().unwrap_or("");
        sa.cmp(sb)
    });

    let n_quarantine = stream_rollups
        .iter()
        .filter(|r| r["status"].as_str() == Some("quarantined"))
        .count() as i64;

    let mut nonq_raw_sum: i64 = 0;
    for (sid, raw) in &raw_by_stream {
        if !compromised.contains(sid) {
            nonq_raw_sum += raw;
        }
    }

    let cap_applied = cap.is_some() && nonq_raw_sum > cap.unwrap();

    let mut scaled_sum: Option<i64> = None;
    if !cap_applied {
        for r in &mut stream_rollups {
            if r["status"].as_str() == Some("ok") {
                let sid = r["stream_id"].as_str().unwrap_or("");
                let raw = *raw_by_stream.get(sid).unwrap_or(&0);
                r.insert("terminal_residue".to_string(), json!(raw));
            }
        }
    } else {
        let c = cap.unwrap();
        let mut sum_scaled: i64 = 0;
        for r in &mut stream_rollups {
            let sid = r["stream_id"].as_str().unwrap_or("").to_string();
            let raw = *raw_by_stream.get(&sid).unwrap_or(&0);
            let tr = if r["status"].as_str() == Some("quarantined") {
                0
            } else if nonq_raw_sum > 0 {
                (raw * c) / nonq_raw_sum
            } else {
                0
            };
            r.insert("terminal_residue".to_string(), json!(tr));
            sum_scaled += tr;
        }
        scaled_sum = Some(sum_scaled);
    }

    let mut meta = Map::new();
    meta.insert("base".to_string(), policy["base"].clone());
    meta.insert(
        "catalog_sha256".to_string(),
        json!(sha256_file(&root.join("catalog.json"))),
    );
    meta.insert("current_day".to_string(), policy["current_day"].clone());
    meta.insert("init".to_string(), policy["init"].clone());
    meta.insert(
        "incidents_sha256".to_string(),
        json!(sha256_file(&root.join("incidents.json"))),
    );
    meta.insert("modulus".to_string(), policy["modulus"].clone());
    meta.insert(
        "policy_sha256".to_string(),
        json!(sha256_file(&root.join("policy.json"))),
    );
    meta.insert(
        "pool_sha256".to_string(),
        json!(sha256_file(&root.join("pool_state.json"))),
    );

    let mut summary = Map::new();
    summary.insert("cap_applied".to_string(), json!(cap_applied));
    summary.insert("quarantined_streams".to_string(), json!(n_quarantine));
    summary.insert(
        "scaled_sum".to_string(),
        match scaled_sum {
            Some(v) => json!(v),
            None => Value::Null,
        },
    );
    summary.insert("streams".to_string(), json!(stream_rollups.len() as i64));
    summary.insert(
        "total_frames_after_suppress".to_string(),
        json!(total_after_suppress),
    );
    summary.insert(
        "total_frames_cataloged".to_string(),
        json!(total_cataloged),
    );

    let mut out = Map::new();
    out.insert("meta".to_string(), Value::Object(meta));
    out.insert(
        "stream_rollups".to_string(),
        Value::Array(
            stream_rollups
                .into_iter()
                .map(Value::Object)
                .collect(),
        ),
    );
    out.insert("summary".to_string(), Value::Object(summary));

    fs::create_dir_all(Path::new("/app/audit")).ok();
    let root_val = sort_keys(Value::Object(out));
    write_json(Path::new(OUT), &root_val);
}
RS

cargo build --release --offline
mkdir -p /app/audit
/app/target/release/modchain
