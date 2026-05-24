mod audit;
mod metrics;
mod report;

use audit::audit_workload;
use report::build_report;
use serde::Deserialize;
use std::fs;
use std::path::Path;

#[derive(Debug, Deserialize)]
struct Policy {
    risk_tiers: std::collections::BTreeMap<String, i64>,
    finding_severity: std::collections::BTreeMap<String, String>,
    severity_ranks: std::collections::BTreeMap<String, i64>,
    syscall_risk_weights: std::collections::BTreeMap<String, i64>,
    policy_syscall_order: Vec<String>,
    tier_syscall_allowlist: std::collections::BTreeMap<String, Vec<String>>,
}

fn main() {
    let policy: Policy =
        serde_json::from_str(&fs::read_to_string("/app/config/policy.json").unwrap()).unwrap();
    let mut paths: Vec<_> = fs::read_dir("/app/data/workloads")
        .unwrap()
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().map(|x| x == "json").unwrap_or(false))
        .collect();
    paths.sort();

    let mut audits = Vec::new();
    let mut findings = Vec::new();
    for path in paths {
        let text = fs::read_to_string(&path).unwrap();
        let workload: audit::WorkloadFile = serde_json::from_str(&text).unwrap();
        let (audit, f) = audit_workload(&workload, &policy);
        findings.extend(f);
        audits.push(audit);
    }

    let report = build_report(audits, findings, &policy);
    fs::create_dir_all("/app/output").ok();
    fs::write(
        "/app/output/capability_policy_audit.json",
        serde_json::to_string_pretty(&report).unwrap() + "\n",
    )
    .unwrap();
}
