use serde::Deserialize;

fn policy_order_index(name: &str, policy: &super::Policy) -> usize {
    policy
        .policy_syscall_order
        .iter()
        .position(|s| s == name)
        .unwrap_or(999)
}

#[derive(Debug, Deserialize)]
pub struct WorkloadFile {
    pub workload_id: String,
    pub risk_tier: String,
    pub required_capabilities: Vec<String>,
    pub observed_capabilities: Vec<String>,
    #[serde(default)]
    pub forbidden_capabilities: Vec<String>,
    pub observed_syscalls: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct WorkloadAudit {
    pub workload_id: String,
    pub risk_tier: String,
    pub risk_tier_rank: i64,
    pub syscall_count: u64,
    pub effective_risk_score: i64,
    pub integrity_lines: u64,
    pub hash_lines: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct Finding {
    pub finding_type: String,
    pub severity: String,
    pub severity_rank: i64,
    pub workload_id: String,
    pub evidence: serde_json::Value,
}

pub fn audit_workload(
    w: &WorkloadFile,
    policy: &super::Policy,
) -> (WorkloadAudit, Vec<Finding>) {
    let tier = &w.risk_tier;
    let tier_rank = *policy.risk_tiers.get(tier).unwrap_or(&0);
    let allow: std::collections::HashSet<String> = policy
        .tier_syscall_allowlist
        .get(tier)
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .collect();

    let mut findings = Vec::new();
    let observed_syscalls = w.observed_syscalls.clone();
    for sc in &observed_syscalls {
        if !allow.contains(sc) {
            findings.push(make_finding(
                policy,
                "syscall_not_allowlisted",
                &w.workload_id,
                serde_json::json!({"syscall": sc, "risk_tier": tier}),
            ));
        }
    }

    let observed_caps: std::collections::HashSet<_> =
        w.observed_capabilities.iter().cloned().collect();
    let required_caps: std::collections::HashSet<_> =
        w.required_capabilities.iter().cloned().collect();
    for cap in &w.required_capabilities {
        if !observed_caps.contains(cap) {
            findings.push(make_finding(
                policy,
                "missing_required_capability",
                &w.workload_id,
                serde_json::json!({"capability": cap}),
            ));
        }
    }

    // Bug: forbidden check uses required_capabilities instead of observed_capabilities
    for cap in &w.forbidden_capabilities {
        if required_caps.contains(cap) {
            findings.push(make_finding(
                policy,
                "forbidden_capability_present",
                &w.workload_id,
                serde_json::json!({"capability": cap}),
            ));
        }
    }

    let mut syscall_risks = Vec::new();
    for sc in &observed_syscalls {
        let risk = policy.syscall_risk_weights.get(sc).copied().unwrap_or(1);
        syscall_risks.push(risk);
    }
    // Bug: sum instead of max
    let effective: i64 = syscall_risks.iter().sum();

    // Bug: lexicographic syscall order for integrity lines
    let mut sorted_syscalls = observed_syscalls.clone();
    sorted_syscalls.sort();
    let hash_lines: Vec<String> = sorted_syscalls
        .iter()
        .map(|sc| {
            let risk = policy.syscall_risk_weights.get(sc).copied().unwrap_or(1);
            format!("{}|{}|{}", w.workload_id, sc, risk)
        })
        .collect();

    let audit = WorkloadAudit {
        workload_id: w.workload_id.clone(),
        risk_tier: tier.clone(),
        risk_tier_rank: tier_rank,
        syscall_count: observed_syscalls.len() as u64,
        effective_risk_score: effective,
        integrity_lines: hash_lines.len() as u64,
        hash_lines,
    };
    (audit, findings)
}

fn make_finding(
    policy: &super::Policy,
    ftype: &str,
    workload_id: &str,
    evidence: serde_json::Value,
) -> Finding {
    let severity = policy
        .finding_severity
        .get(ftype)
        .cloned()
        .unwrap_or_else(|| "medium".to_string());
    let severity_rank = *policy.severity_ranks.get(&severity).unwrap_or(&3);
    Finding {
        finding_type: ftype.to_string(),
        severity,
        severity_rank,
        workload_id: workload_id.to_string(),
        evidence,
    }
}
