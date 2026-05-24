use crate::audit::{Finding, WorkloadAudit};
use crate::metrics;
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;

#[derive(Serialize)]
pub struct Report {
    schema_version: u64,
    source_hashes: BTreeMap<String, String>,
    workload_audits: Vec<WorkloadAuditOut>,
    findings: Vec<FindingOut>,
    summary: SummaryOut,
}

#[derive(Serialize)]
struct WorkloadAuditOut {
    workload_id: String,
    risk_tier: String,
    risk_tier_rank: i64,
    syscall_count: u64,
    effective_risk_score: i64,
    integrity_lines: u64,
}

#[derive(Serialize)]
struct FindingOut {
    finding_type: String,
    severity: String,
    severity_rank: i64,
    workload_id: String,
    evidence: serde_json::Value,
}

#[derive(Serialize)]
struct SummaryOut {
    workload_count: u64,
    total_findings: u64,
    findings_by_type: BTreeMap<String, u64>,
    findings_by_severity: BTreeMap<String, u64>,
    avg_effective_risk_score: f64,
    integrity_hash: String,
}

pub fn build_report(
    mut audits: Vec<WorkloadAudit>,
    mut findings: Vec<Finding>,
    _policy: &super::Policy,
) -> Report {
    audits.sort_by(|a, b| a.workload_id.cmp(&b.workload_id));

    findings.sort_by(|a, b| {
        (&a.workload_id, &a.finding_type).cmp(&(&b.workload_id, &b.finding_type))
    });

    let mut hash_lines: Vec<String> = Vec::new();
    for audit in &audits {
        hash_lines.extend(audit.hash_lines.clone());
    }
    let integrity_hash = {
        let body = hash_lines.join("\n");
        let mut hasher = Sha256::new();
        hasher.update(body.as_bytes());
        format!("{:x}", hasher.finalize())
    };

    let mut source_hashes = BTreeMap::new();
    let mut paths: Vec<_> = fs::read_dir("/app/data/workloads")
        .unwrap()
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().map(|x| x == "json").unwrap_or(false))
        .collect();
    paths.sort();
    for p in paths {
        let rel = format!(
            "data/workloads/{}",
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

    let mut pol_text = fs::read_to_string("/app/config/policy.json").unwrap();
    pol_text = pol_text.replace("\r\n", "\n");
    if pol_text.ends_with('\n') {
        pol_text.pop();
    }
    let mut hasher = Sha256::new();
    hasher.update(pol_text.as_bytes());
    source_hashes.insert(
        "config/policy.json".to_string(),
        format!("{:x}", hasher.finalize()),
    );

    let effective_scores: Vec<i64> = audits
        .iter()
        .map(|a| a.effective_risk_score)
        .filter(|&s| s > 0)
        .collect();
    let avg_risk = metrics::avg_effective_arithmetic(&effective_scores);

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

    let workload_out: Vec<WorkloadAuditOut> = audits
        .iter()
        .map(|a| WorkloadAuditOut {
            workload_id: a.workload_id.clone(),
            risk_tier: a.risk_tier.clone(),
            risk_tier_rank: a.risk_tier_rank,
            syscall_count: a.syscall_count,
            effective_risk_score: a.effective_risk_score,
            integrity_lines: a.integrity_lines,
        })
        .collect();

    let findings_out: Vec<FindingOut> = findings
        .iter()
        .map(|f| FindingOut {
            finding_type: f.finding_type.clone(),
            severity: f.severity.clone(),
            severity_rank: f.severity_rank,
            workload_id: f.workload_id.clone(),
            evidence: f.evidence.clone(),
        })
        .collect();

    Report {
        schema_version: 1,
        source_hashes,
        workload_audits: workload_out,
        findings: findings_out,
        summary: SummaryOut {
            workload_count: audits.len() as u64,
            total_findings: findings.len() as u64,
            findings_by_type: fbt,
            findings_by_severity: fbs,
            avg_effective_risk_score: avg_risk,
            integrity_hash,
        },
    }
}
