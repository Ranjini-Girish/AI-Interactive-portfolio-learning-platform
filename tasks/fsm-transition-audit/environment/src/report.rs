use crate::metrics;
use crate::replay::{Finding, PolicyView, WorkflowAudit};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;

#[derive(Serialize)]
pub struct Report {
    schema_version: u64,
    source_hashes: BTreeMap<String, String>,
    workflow_audits: Vec<WorkflowAuditOut>,
    findings: Vec<FindingOut>,
    summary: SummaryOut,
}

#[derive(Serialize)]
struct WorkflowAuditOut {
    workflow_id: String,
    fsm_id: String,
    transitions_kept: u64,
    transitions_skipped: u64,
    final_state: String,
    states_visited: u64,
    avg_dwell_ms: f64,
    integrity_lines: u64,
}

#[derive(Serialize)]
struct FindingOut {
    finding_type: String,
    severity: String,
    severity_rank: i64,
    workflow_id: String,
    transition_id: Option<String>,
    evidence: serde_json::Value,
}

#[derive(Serialize)]
struct SummaryOut {
    workflow_count: u64,
    total_transitions_kept: u64,
    total_transitions_skipped: u64,
    total_findings: u64,
    findings_by_type: BTreeMap<String, u64>,
    findings_by_severity: BTreeMap<String, u64>,
    avg_workflow_dwell_ms: f64,
    integrity_hash: String,
}

pub fn build_report(
    mut audits: Vec<WorkflowAudit>,
    mut findings: Vec<Finding>,
    _policy: &crate::Policy,
) -> Report {
    audits.sort_by(|a, b| a.workflow_id.cmp(&b.workflow_id));

    findings.sort_by(|a, b| {
        (
            a.severity_rank,
            &a.finding_type,
            &a.workflow_id,
            &a.transition_id,
        )
            .cmp(&(
                b.severity_rank,
                &b.finding_type,
                &b.workflow_id,
                &b.transition_id,
            ))
    });

    let mut hash_lines: Vec<String> = Vec::new();
    for audit in &audits {
        let mut trs = audit.kept_transitions.clone();
        trs.sort_by(|a, b| a.transition_id.cmp(&b.transition_id));
        for tr in trs {
            hash_lines.push(format!(
                "{}|{}|{}|{}",
                audit.workflow_id, tr.transition_id, tr.sequence, tr.to_state
            ));
        }
    }
    let integrity_hash = {
        let body = hash_lines.join("\n");
        let mut hasher = Sha256::new();
        hasher.update(body.as_bytes());
        format!("{:x}", hasher.finalize())
    };

    let mut source_hashes = BTreeMap::new();
    for sub in ["workflows", "fsm_defs"] {
        let dir = format!("/app/data/{}", sub);
        let mut paths: Vec<_> = fs::read_dir(&dir)
            .unwrap()
            .filter_map(|e| e.ok())
            .map(|e| e.path())
            .filter(|p| p.extension().map(|x| x == "json").unwrap_or(false))
            .collect();
        paths.sort();
        for p in paths {
            let rel = format!(
                "data/{}/{}",
                sub,
                p.file_name().unwrap().to_string_lossy()
            );
            let mut text = fs::read_to_string(&p).unwrap();
            text = text.replace("\r\n", "\n");
            if text.ends_with('\n') {
                text.pop();
            }
            let mut hasher = Sha256::new();
            hasher.update(text.as_bytes());
            source_hashes.insert(rel, format!("{:x}", hasher.finalize()));
        }
    }

    let wf_latencies: Vec<f64> = audits.iter().map(|a| a.avg_dwell_ms).collect();
    let avg_workflow = metrics::harmonic_mean(&wf_latencies);

    let mut fbt = BTreeMap::new();
    for f in &findings {
        *fbt.entry(f.finding_type.clone()).or_insert(0) += 1;
    }
    let mut fbs = BTreeMap::new();
    for sev in ["critical", "high", "medium", "low", "info"] {
        fbs.insert(sev.to_string(), 0);
    }
    for f in &findings {
        *fbs.entry(f.severity.clone()).or_insert(0) += 1;
    }

    let workflow_out: Vec<WorkflowAuditOut> = audits
        .iter()
        .map(|a| WorkflowAuditOut {
            workflow_id: a.workflow_id.clone(),
            fsm_id: a.fsm_id.clone(),
            transitions_kept: a.transitions_kept,
            transitions_skipped: a.transitions_skipped,
            final_state: a.final_state.clone(),
            states_visited: a.states_visited,
            avg_dwell_ms: a.avg_dwell_ms,
            integrity_lines: a.integrity_lines,
        })
        .collect();

    let findings_out: Vec<FindingOut> = findings
        .iter()
        .map(|f| FindingOut {
            finding_type: f.finding_type.clone(),
            severity: f.severity.clone(),
            severity_rank: f.severity_rank,
            workflow_id: f.workflow_id.clone(),
            transition_id: f.transition_id.clone(),
            evidence: f.evidence.clone(),
        })
        .collect();

    Report {
        schema_version: 1,
        source_hashes,
        workflow_audits: workflow_out,
        findings: findings_out,
        summary: SummaryOut {
            workflow_count: audits.len() as u64,
            total_transitions_kept: audits.iter().map(|a| a.transitions_kept).sum(),
            total_transitions_skipped: audits.iter().map(|a| a.transitions_skipped).sum(),
            total_findings: findings.len() as u64,
            findings_by_type: fbt,
            findings_by_severity: fbs,
            avg_workflow_dwell_ms: avg_workflow,
            integrity_hash,
        },
    }
}
