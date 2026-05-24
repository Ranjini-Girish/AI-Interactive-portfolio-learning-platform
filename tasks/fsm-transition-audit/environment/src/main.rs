mod metrics;
mod replay;
mod report;

use replay::replay_workflow;
use report::build_report;
use serde::Deserialize;
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

#[derive(Debug, Deserialize)]
struct Policy {
    finding_severity: BTreeMap<String, String>,
    severity_ranks: BTreeMap<String, i64>,
}

fn main() {
    let policy: Policy =
        serde_json::from_str(&fs::read_to_string("/app/config/policy.json").unwrap()).unwrap();

    let mut fsm_defs = BTreeMap::new();
    for entry in fs::read_dir("/app/data/fsm_defs").unwrap() {
        let path = entry.unwrap().path();
        if path.extension().map(|e| e == "json").unwrap_or(false) {
            let def: replay::FsmDef = serde_json::from_str(&fs::read_to_string(&path).unwrap())
                .unwrap();
            fsm_defs.insert(def.fsm_id.clone(), def);
        }
    }

    let mut workflow_paths: Vec<_> = fs::read_dir("/app/data/workflows")
        .unwrap()
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().map(|x| x == "json").unwrap_or(false))
        .collect();
    workflow_paths.sort();

    let mut audits = Vec::new();
    let mut all_findings = Vec::new();
    for path in workflow_paths {
        let wf: replay::WorkflowFile =
            serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        let fsm = fsm_defs.get(&wf.fsm_id).expect("unknown fsm_id");
        let (audit, findings) = replay_workflow(&wf, fsm, &policy);
        all_findings.extend(findings);
        audits.push(audit);
    }

    let report = build_report(audits, all_findings, &policy);
    fs::create_dir_all("/app/output").ok();
    fs::write(
        "/app/output/fsm_audit_report.json",
        serde_json::to_string_pretty(&report).unwrap() + "\n",
    )
    .unwrap();
}
