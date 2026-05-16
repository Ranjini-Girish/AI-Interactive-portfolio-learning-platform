#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/local/cargo/bin:${PATH:-}"
cd /app
mkdir -p src output

cat > Cargo.toml <<'EOF'
[package]
name = "gossipledger"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1.0.210", features = ["derive"] }
serde_json = "1.0.128"
EOF

cat > src/main.rs <<'RS'
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;

#[derive(Clone)]
struct Ev {
    r: i64,
    a: String,
    b: String,
    verb: String,
    u: String,
}

#[derive(Serialize)]
struct Per {
    first_round: i64,
    last_round: i64,
    propagation_delay: i64,
}

#[derive(Serialize)]
struct Report {
    canonical_replay: Vec<String>,
    edge_totals: BTreeMap<String, i64>,
    max_round: i64,
    nodes: Vec<String>,
    per_update: BTreeMap<String, Per>,
    pull_last_hits: i64,
    round_snapshots: BTreeMap<String, BTreeMap<String, Vec<String>>>,
}

fn all_digits(s: &str) -> bool {
    !s.is_empty() && s.chars().all(|c| c.is_ascii_digit())
}

fn cmp_id(a: &str, b: &str) -> std::cmp::Ordering {
    match (all_digits(a), all_digits(b)) {
        (true, true) => a
            .parse::<u128>()
            .unwrap()
            .cmp(&b.parse::<u128>().unwrap()),
        _ => a.cmp(b),
    }
}

fn strip_line(s: &str) -> &str {
    let t = s.trim_start();
    t.split('#').next().unwrap_or("").trim()
}

fn parse_file(path: &str) -> Vec<Ev> {
    let text = fs::read_to_string(path).expect("read inbox");
    let mut out = Vec::new();
    for raw in text.lines() {
        let line = strip_line(raw);
        if line.is_empty() {
            continue;
        }
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() != 5 {
            panic!("parse error: {}", line);
        }
        let r: i64 = parts[0].parse().expect("round");
        let verb = parts[3].to_string();
        if verb != "push" && verb != "pull" {
            panic!("verb");
        }
        out.push(Ev {
            r,
            a: parts[1].to_string(),
            b: parts[2].to_string(),
            verb,
            u: parts[4].to_string(),
        });
    }
    out
}

fn sort_nodes(s: &BTreeSet<String>) -> Vec<String> {
    s.iter().cloned().collect()
}

fn sort_uids(s: &BTreeSet<String>) -> Vec<String> {
    let mut v: Vec<String> = s.iter().cloned().collect();
    v.sort_by(|x, y| cmp_id(x, y));
    v
}

fn main() {
    let p1 = "/app/gossip_lab/inbox/events.log";
    let p2 = "/app/gossip_lab/inbox/events_overflow.log";
    let mut stream = parse_file(p1);
    stream.extend(parse_file(p2));

    let mut nodes: BTreeSet<String> = BTreeSet::new();
    let mut marks: BTreeSet<(String, String)> = BTreeSet::new();
    let mut first: BTreeMap<String, i64> = BTreeMap::new();
    let mut last: BTreeMap<String, i64> = BTreeMap::new();
    let mut edges: BTreeMap<String, i64> = BTreeMap::new();
    let mut last_idx: BTreeMap<String, usize> = BTreeMap::new();
    let mut uids: BTreeSet<String> = BTreeSet::new();
    let mut canon: Vec<String> = Vec::new();

    for (idx, e) in stream.iter().enumerate() {
        nodes.insert(e.a.clone());
        nodes.insert(e.b.clone());
        marks.insert((e.a.clone(), e.u.clone()));
        marks.insert((e.b.clone(), e.u.clone()));
        uids.insert(e.u.clone());
        first
            .entry(e.u.clone())
            .and_modify(|v| *v = (*v).min(e.r))
            .or_insert(e.r);
        last.entry(e.u.clone())
            .and_modify(|v| *v = (*v).max(e.r))
            .or_insert(e.r);
        let ek = format!("{}>{}", e.a, e.b);
        *edges.entry(ek).or_insert(0) += 1;
        last_idx.insert(e.u.clone(), idx);
        canon.push(format!(
            "{} {} {} {} {}",
            e.r, e.a, e.b, e.verb, e.u
        ));
    }

    let node_list = sort_nodes(&nodes);
    let uid_list = sort_uids(&uids);
    let max_round = stream.iter().map(|e| e.r).max().unwrap_or(0);

    let mut pull_last_hits: i64 = 0;
    for u in &uid_list {
        let li = *last_idx.get(u).expect("idx");
        if stream[li].verb == "pull" {
            pull_last_hits += 1;
        }
    }

    let mut per_update: BTreeMap<String, Per> = BTreeMap::new();
    for u in &uid_list {
        let fr = *first.get(u).unwrap();
        let lr = *last.get(u).unwrap();
        per_update.insert(
            u.clone(),
            Per {
                first_round: fr,
                last_round: lr,
                propagation_delay: lr - fr + 1,
            },
        );
    }

    let mut round_snapshots: BTreeMap<String, BTreeMap<String, Vec<String>>> = BTreeMap::new();
    for k in 1..=max_round {
        let mut snap: BTreeMap<String, Vec<String>> = BTreeMap::new();
        for n in &node_list {
            let mut have: Vec<String> = Vec::new();
            for u in &uid_list {
                let fr = *first.get(u).unwrap();
                if fr <= k && marks.contains(&(n.clone(), u.clone())) {
                    have.push(u.clone());
                }
            }
            snap.insert(n.clone(), have);
        }
        round_snapshots.insert(k.to_string(), snap);
    }

    let rep = Report {
        canonical_replay: canon,
        edge_totals: edges,
        max_round,
        nodes: node_list,
        per_update,
        pull_last_hits,
        round_snapshots,
    };

    let mut s = serde_json::to_string_pretty(&rep).expect("json");
    s.push('\n');
    fs::create_dir_all("/app/output").expect("mkdir");
    fs::write("/app/output/gossip_report.json", s).expect("write");
}
RS

cargo build --release
/app/target/release/gossipledger
