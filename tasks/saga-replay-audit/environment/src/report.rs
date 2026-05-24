use crate::metrics;
use crate::replay::{Finding, PolicyView, SagaAudit};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

#[derive(Serialize)]
pub struct Report {
    schema_version: u64,
    source_hashes: BTreeMap<String, String>,
    saga_audits: Vec<SagaAuditOut>,
    findings: Vec<FindingOut>,
    summary: SummaryOut,
}

#[derive(Serialize)]
struct SagaAuditOut {
    saga_id: String,
    events_kept: u64,
    events_skipped: u64,
    steps_completed: u64,
    steps_compensated: u64,
    compensation_events: u64,
    avg_step_latency_ms: f64,
    integrity_lines: u64,
}

#[derive(Serialize)]
struct FindingOut {
    finding_type: String,
    severity: String,
    severity_rank: i64,
    saga_id: String,
    event_id: Option<String>,
    step: Option<String>,
    evidence: serde_json::Value,
}

#[derive(Serialize)]
struct SummaryOut {
    saga_count: u64,
    total_events_kept: u64,
    total_events_skipped: u64,
    total_findings: u64,
    findings_by_type: BTreeMap<String, u64>,
    findings_by_severity: BTreeMap<String, u64>,
    avg_saga_latency_ms: f64,
    integrity_hash: String,
}

pub fn build_report(
    mut audits: Vec<SagaAudit>,
    mut findings: Vec<Finding>,
    policy: &crate::Policy,
) -> Report {
    audits.sort_by(|a, b| a.saga_id.cmp(&b.saga_id));

    findings.sort_by(|a, b| {
        (
            a.severity_rank,
            &a.finding_type,
            &a.saga_id,
            &a.event_id,
            &a.step,
        )
            .cmp(&(
                b.severity_rank,
                &b.finding_type,
                &b.saga_id,
                &b.event_id,
                &b.step,
            ))
    });

    let mut hash_lines: Vec<String> = Vec::new();
    for audit in &audits {
        let mut evs = audit.kept_events.clone();
        evs.sort_by(|a, b| a.event_id.cmp(&b.event_id));
        for ev in evs {
            hash_lines.push(format!(
                "{}|{}|{}|{}",
                audit.saga_id, ev.event_id, ev.sequence, ev.status
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
    let mut paths: Vec<_> = fs::read_dir("/app/data/sagas")
        .unwrap()
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().map(|x| x == "json").unwrap_or(false))
        .collect();
    paths.sort();
    for p in paths {
        let rel = format!("data/sagas/{}", p.file_name().unwrap().to_string_lossy());
        let mut text = fs::read_to_string(&p).unwrap();
        text = text.replace("\r\n", "\n");
        if text.ends_with('\n') {
            text.pop();
        }
        let mut hasher = Sha256::new();
        hasher.update(text.as_bytes());
        source_hashes.insert(rel, format!("{:x}", hasher.finalize()));
    }

    let saga_latencies: Vec<f64> = audits.iter().map(|a| a.avg_step_latency_ms).collect();
    let avg_saga = metrics::harmonic_mean(&saga_latencies);

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

    let saga_out: Vec<SagaAuditOut> = audits
        .iter()
        .map(|a| SagaAuditOut {
            saga_id: a.saga_id.clone(),
            events_kept: a.events_kept,
            events_skipped: a.events_skipped,
            steps_completed: a.steps_completed,
            steps_compensated: a.steps_compensated,
            compensation_events: a.compensation_events,
            avg_step_latency_ms: a.avg_step_latency_ms,
            integrity_lines: a.integrity_lines,
        })
        .collect();

    let findings_out: Vec<FindingOut> = findings
        .iter()
        .map(|f| FindingOut {
            finding_type: f.finding_type.clone(),
            severity: f.severity.clone(),
            severity_rank: f.severity_rank,
            saga_id: f.saga_id.clone(),
            event_id: f.event_id.clone(),
            step: f.step.clone(),
            evidence: f.evidence.clone(),
        })
        .collect();

    let total_events_kept: u64 = audits.iter().map(|a| a.events_kept).sum();
    let total_events_skipped: u64 = audits.iter().map(|a| a.events_skipped).sum();

    Report {
        schema_version: 1,
        source_hashes,
        saga_audits: saga_out,
        findings: findings_out,
        summary: SummaryOut {
            saga_count: audits.len() as u64,
            total_events_kept,
            total_events_skipped,
            total_findings: findings.len() as u64,
            findings_by_type: fbt,
            findings_by_severity: fbs,
            avg_saga_latency_ms: avg_saga,
            integrity_hash,
        },
    }
}
