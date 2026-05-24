mod metrics;
mod replay;
mod report;

use replay::replay_saga;
use report::build_report;
use serde::Deserialize;
use std::fs;
use std::path::Path;

#[derive(Debug, Deserialize)]
struct Policy {
    finding_severity: std::collections::BTreeMap<String, String>,
    severity_ranks: std::collections::BTreeMap<String, i64>,
}

fn main() {
    let policy: Policy =
        serde_json::from_str(&fs::read_to_string("/app/config/policy.json").unwrap()).unwrap();
    let mut saga_paths: Vec<_> = fs::read_dir("/app/data/sagas")
        .unwrap()
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().map(|x| x == "json").unwrap_or(false))
        .collect();
    saga_paths.sort();

    let mut audits = Vec::new();
    let mut all_findings = Vec::new();
    for path in saga_paths {
        let text = fs::read_to_string(&path).unwrap();
        let saga: replay::SagaFile = serde_json::from_str(&text).unwrap();
        let (audit, findings) = replay_saga(&saga, &policy);
        all_findings.extend(findings);
        audits.push(audit);
    }

    let report = build_report(audits, all_findings, &policy);
    fs::create_dir_all("/app/output").ok();
    fs::write(
        "/app/output/saga_replay_audit.json",
        serde_json::to_string_pretty(&report).unwrap() + "\n",
    )
    .unwrap();
}
