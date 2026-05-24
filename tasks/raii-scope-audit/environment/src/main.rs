mod metrics;
mod replay;
mod report;

use serde::Deserialize;
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

#[derive(Debug, Deserialize)]
pub struct Policy {
    pub finding_severity: BTreeMap<String, String>,
    pub severity_ranks: BTreeMap<String, i64>,
}

fn main() {
    let policy: Policy = serde_json::from_str(
        &fs::read_to_string("/app/config/policy.json").expect("policy"),
    )
    .expect("parse policy");
    let pv = replay::PolicyView::from_policy(&policy);
    let mut audits = Vec::new();
    let mut findings = Vec::new();
    for entry in fs::read_dir("/app/data/workloads").expect("workloads dir") {
        let path = entry.expect("entry").path();
        if path.extension().and_then(|s| s.to_str()) != Some("json") {
            continue;
        }
        let text = fs::read_to_string(&path).expect("read workload");
        let wf: replay::WorkloadFile = serde_json::from_str(&text).expect("parse workload");
        let (audit, mut f) = replay::replay_workload(&wf, &pv);
        findings.append(&mut f);
        audits.push(audit);
    }
    report::write_report(&policy, audits, findings);
}
