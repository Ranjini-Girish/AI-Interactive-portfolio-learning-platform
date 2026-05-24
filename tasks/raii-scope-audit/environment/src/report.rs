use crate::replay::{Finding, WorkloadAudit};
use crate::Policy;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

pub fn source_hash(path: &Path) -> String {
    let mut text = fs::read_to_string(path).expect("read");
    text = text.replace("\r\n", "\n");
    if text.ends_with('\n') {
        text.pop();
    }
    let mut h = Sha256::new();
    h.update(text.as_bytes());
    format!("{:x}", h.finalize())
}

pub fn write_report(policy: &Policy, mut audits: Vec<WorkloadAudit>, mut findings: Vec<Finding>) {
    audits.sort_by(|a, b| a.workload_id.cmp(&b.workload_id));
    findings.sort_by(|a, b| {
        (
            a.severity_rank,
            a.finding_type.as_str(),
            a.workload_id.as_str(),
            a.event_id.as_deref().unwrap_or(""),
        )
            .cmp(&(
                b.severity_rank,
                b.finding_type.as_str(),
                b.workload_id.as_str(),
                b.event_id.as_deref().unwrap_or(""),
            ))
    });
    let mut lines: Vec<String> = Vec::new();
    for a in &audits {
        for e in &a.kept_events {
            lines.push(format!(
                "{}|{}|{}|{}|{}",
                a.workload_id, e.event_id, e.sequence, e.kind, e.scope_id
            ));
        }
    }
    let integrity = {
        let mut h = Sha256::new();
        h.update(lines.join("\n").as_bytes());
        format!("{:x}", h.finalize())
    };
    let mut source_hashes = BTreeMap::new();
    for entry in fs::read_dir("/app/data/workloads").expect("dir") {
        let p = entry.expect("e").path();
        if p.extension().and_then(|s| s.to_str()) == Some("json") {
            let rel = format!("data/workloads/{}", p.file_name().unwrap().to_string_lossy());
            source_hashes.insert(rel, source_hash(&p));
        }
    }
    let holds: Vec<f64> = audits.iter().map(|a| a.avg_hold_ms).filter(|v| *v > 0.0).collect();
    let avg_wl = crate::metrics::harmonic_mean(&holds);
    let mut by_type: BTreeMap<String, u64> = BTreeMap::new();
    let mut by_sev: BTreeMap<String, u64> = BTreeMap::new();
    for k in policy.severity_ranks.keys() {
        by_sev.insert(k.clone(), 0);
    }
    for f in &findings {
        *by_type.entry(f.finding_type.clone()).or_insert(0) += 1;
        *by_sev.entry(f.severity.clone()).or_insert(0) += 1;
    }
    let workload_audits: Vec<serde_json::Value> = audits
        .iter()
        .map(|a| {
            serde_json::json!({
                "workload_id": a.workload_id,
                "events_kept": a.events_kept,
                "events_skipped": a.events_skipped,
                "max_stack_depth": a.max_stack_depth,
                "scopes_leaked": a.scopes_leaked,
                "avg_hold_ms": a.avg_hold_ms,
                "integrity_lines": a.integrity_lines,
            })
        })
        .collect();
    let report = serde_json::json!({
        "schema_version": 1,
        "source_hashes": source_hashes,
        "workload_audits": workload_audits,
        "findings": findings.iter().map(|f| serde_json::json!({
            "finding_type": f.finding_type,
            "severity": f.severity,
            "severity_rank": f.severity_rank,
            "workload_id": f.workload_id,
            "event_id": f.event_id,
            "evidence": f.evidence,
        })).collect::<Vec<_>>(),
        "summary": {
            "workload_count": audits.len(),
            "events_kept_total": audits.iter().map(|a| a.events_kept).sum::<u64>(),
            "events_skipped_total": audits.iter().map(|a| a.events_skipped).sum::<u64>(),
            "findings_by_type": by_type,
            "findings_by_severity": by_sev,
            "avg_workload_hold_ms": avg_wl,
            "integrity_hash": integrity,
        }
    });
    fs::create_dir_all("/app/output").ok();
    let out = serde_json::to_string_pretty(&report).expect("serialize");
    fs::write("/app/output/scope_audit_report.json", format!("{}\n", out)).expect("write");
}
