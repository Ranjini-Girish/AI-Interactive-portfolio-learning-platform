use crate::metrics;
use serde::Deserialize;
use std::collections::{BTreeMap, HashSet};

#[derive(Debug, Clone, Deserialize)]
pub struct ScopeEvent {
    pub event_id: String,
    pub sequence: u64,
    pub logged_at: String,
    pub kind: String,
    pub scope_id: String,
    pub hold_ms: Option<u64>,
}

#[derive(Debug, Deserialize)]
pub struct WorkloadFile {
    pub workload_id: String,
    pub events: Vec<ScopeEvent>,
}

#[derive(Debug, Clone)]
pub struct PolicyView {
    pub finding_severity: BTreeMap<String, String>,
    pub severity_ranks: BTreeMap<String, i64>,
}

#[derive(Debug, Clone)]
pub struct WorkloadAudit {
    pub workload_id: String,
    pub events_kept: u64,
    pub events_skipped: u64,
    pub max_stack_depth: u64,
    pub scopes_leaked: u64,
    pub avg_hold_ms: f64,
    pub integrity_lines: u64,
    pub kept_events: Vec<ScopeEvent>,
}

#[derive(Debug, Clone)]
pub struct Finding {
    pub finding_type: String,
    pub severity: String,
    pub severity_rank: i64,
    pub workload_id: String,
    pub event_id: Option<String>,
    pub evidence: serde_json::Value,
}

impl PolicyView {
    pub fn from_policy(p: &super::Policy) -> Self {
        PolicyView {
            finding_severity: p.finding_severity.clone(),
            severity_ranks: p.severity_ranks.clone(),
        }
    }
}

fn sort_events(events: &mut [ScopeEvent]) {
    events.sort_by(|a, b| a.logged_at.cmp(&b.logged_at));
}

pub fn replay_workload(wf: &WorkloadFile, pv: &PolicyView) -> (WorkloadAudit, Vec<Finding>) {
    let mut events = wf.events.clone();
    sort_events(&mut events);
    let mut findings = Vec::new();
    let mut kept = Vec::new();
    let mut seen_seq: HashSet<u64> = HashSet::new();
    let mut stack: Vec<String> = Vec::new();
    let mut max_depth: u64 = 0;
    let mut hold_vals: Vec<f64> = Vec::new();
    let mut panic_target: Option<String> = None;
    let mut skipped: u64 = 0;

    for ev in events {
        if seen_seq.contains(&ev.sequence) {
            skipped += 1;
            findings.push(make_finding(pv, "duplicate_event_skipped", &wf.workload_id, Some(ev.event_id.clone()), serde_json::json!({"duplicate_sequence": ev.sequence})));
            continue;
        }
        seen_seq.insert(ev.sequence);
        match ev.kind.as_str() {
            "enter" => {
                if stack.contains(&ev.scope_id) {
                    findings.push(make_finding(pv, "scope_reentered", &wf.workload_id, Some(ev.event_id.clone()), serde_json::json!({"scope_id": ev.scope_id})));
                }
                stack.push(ev.scope_id.clone());
                max_depth = max_depth.max(stack.len() as u64);
            }
            "panic_mark" => {
                if stack.is_empty() {
                    findings.push(make_finding(pv, "exit_without_enter", &wf.workload_id, Some(ev.event_id.clone()), serde_json::json!({})));
                } else {
                    panic_target = stack.last().cloned();
                }
            }
            "exit" => {
                if stack.is_empty() {
                    findings.push(make_finding(pv, "exit_without_enter", &wf.workload_id, Some(ev.event_id.clone()), serde_json::json!({})));
                } else {
                    stack.pop();
                    if let Some(h) = ev.hold_ms {
                        if h > 0 {
                            hold_vals.push(h as f64);
                        }
                    }
                }
            }
            _ => {}
        }
        kept.push(ev);
    }

    let avg_hold = metrics::arithmetic_mean(&hold_vals);
    let audit = WorkloadAudit {
        workload_id: wf.workload_id.clone(),
        events_kept: kept.len() as u64,
        events_skipped: skipped,
        max_stack_depth: max_depth,
        scopes_leaked: 0,
        avg_hold_ms: avg_hold,
        integrity_lines: kept.len() as u64,
        kept_events: kept,
    };
    (audit, findings)
}

pub fn make_finding(
    pv: &PolicyView,
    ftype: &str,
    workload_id: &str,
    event_id: Option<String>,
    evidence: serde_json::Value,
) -> Finding {
    let sev = pv.finding_severity.get(ftype).cloned().unwrap_or_else(|| "low".to_string());
    let rank = *pv.severity_ranks.get(&sev).unwrap_or(&0);
    Finding {
        finding_type: ftype.to_string(),
        severity: sev,
        severity_rank: rank,
        workload_id: workload_id.to_string(),
        event_id,
        evidence,
    }
}
