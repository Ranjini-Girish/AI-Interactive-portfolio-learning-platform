use crate::metrics;
use serde::Deserialize;
use std::collections::{BTreeMap, HashSet, HashMap};

#[derive(Debug, Clone, Deserialize)]
pub struct SagaEvent {
    pub event_id: String,
    pub sequence: u64,
    pub timestamp_ms: u64,
    pub step: String,
    pub status: String,
    pub duration_ms: Option<u64>,
    pub parent_event_id: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct SagaFile {
    pub saga_id: String,
    pub events: Vec<SagaEvent>,
}

#[derive(Debug, Clone)]
pub struct PolicyView {
    pub finding_severity: BTreeMap<String, String>,
    pub severity_ranks: BTreeMap<String, i64>,
}

#[derive(Debug, Clone)]
pub struct SagaAudit {
    pub saga_id: String,
    pub events_kept: u64,
    pub events_skipped: u64,
    pub steps_completed: u64,
    pub steps_compensated: u64,
    pub compensation_events: u64,
    pub avg_step_latency_ms: f64,
    pub integrity_lines: u64,
    pub kept_events: Vec<SagaEvent>,
}

#[derive(Debug, Clone)]
pub struct Finding {
    pub finding_type: String,
    pub severity: String,
    pub severity_rank: i64,
    pub saga_id: String,
    pub event_id: Option<String>,
    pub step: Option<String>,
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

fn sort_events(events: &mut [SagaEvent]) {
    events.sort_by(|a, b| a.timestamp_ms.cmp(&b.timestamp_ms));
}

pub fn replay_saga(saga: &SagaFile, policy: &super::Policy) -> (SagaAudit, Vec<Finding>) {
    let pv = PolicyView::from_policy(policy);
    let mut events = saga.events.clone();
    sort_events(&mut events);

    let mut findings = Vec::new();
    let mut kept: Vec<SagaEvent> = Vec::new();
    let mut seen_ids: HashSet<String> = HashSet::new();
    let mut skipped = 0u64;

    for ev in events {
        if seen_ids.contains(&ev.event_id) {
            skipped += 1;
            let ftype = "duplicate_event_skipped";
            findings.push(make_finding(
                &pv,
                ftype,
                &saga.saga_id,
                Some(ev.event_id.clone()),
                Some(ev.step.clone()),
                serde_json::json!({"duplicate_sequence": ev.sequence}),
            ));
            continue;
        }
        seen_ids.insert(ev.event_id.clone());
        kept.push(ev);
    }

    for i in 1..kept.len() {
        if kept[i].timestamp_ms < kept[i - 1].timestamp_ms {
            let ftype = "out_of_order_timestamp";
            findings.push(make_finding(
                &pv,
                ftype,
                &saga.saga_id,
                Some(kept[i].event_id.clone()),
                Some(kept[i].step.clone()),
                serde_json::json!({
                    "previous_timestamp_ms": kept[i-1].timestamp_ms,
                    "timestamp_ms": kept[i].timestamp_ms
                }),
            ));
        }
    }

    let kept_ids: HashSet<_> = kept.iter().map(|e| e.event_id.clone()).collect();
    for ev in &kept {
        if let Some(ref pid) = ev.parent_event_id {
            if !kept_ids.contains(pid) {
                let ftype = "orphan_parent";
                findings.push(make_finding(
                    &pv,
                    ftype,
                    &saga.saga_id,
                    Some(ev.event_id.clone()),
                    Some(ev.step.clone()),
                    serde_json::json!({"parent_event_id": pid}),
                ));
            }
        }
    }

    let mut step_state: HashMap<String, i8> = HashMap::new();
    for ev in &kept {
        match ev.status.as_str() {
            "started" => {
                step_state.insert(ev.step.clone(), 1);
            }
            "completed" => {
                step_state.insert(ev.step.clone(), 2);
            }
            "compensated" => {
                step_state.insert(ev.step.clone(), 3);
            }
            _ => {}
        }
    }

    for (step, st) in &step_state {
        if *st == 1 {
            let ftype = "stalled_step";
            findings.push(make_finding(
                &pv,
                ftype,
                &saga.saga_id,
                None,
                Some(step.clone()),
                serde_json::json!({"step": step}),
            ));
        }
    }

    let compensated: Vec<_> = kept
        .iter()
        .filter(|e| e.status == "compensated")
        .collect();
    for i in 1..compensated.len() {
        if compensated[i].sequence >= compensated[i - 1].sequence {
            let ftype = "compensation_order_violation";
            findings.push(make_finding(
                &pv,
                ftype,
                &saga.saga_id,
                Some(compensated[i].event_id.clone()),
                Some(compensated[i].step.clone()),
                serde_json::json!({
                    "previous_sequence": compensated[i-1].sequence,
                    "sequence": compensated[i].sequence
                }),
            ));
        }
    }

    let steps_completed = step_state.values().filter(|&&s| s == 2).count() as u64;
    let steps_compensated = step_state.values().filter(|&&s| s == 3).count() as u64;
    let compensation_events = compensated.len() as u64;

    let avg = metrics::avg_latency_arithmetic(&kept);

    let audit = SagaAudit {
        saga_id: saga.saga_id.clone(),
        events_kept: kept.len() as u64,
        events_skipped: skipped,
        steps_completed,
        steps_compensated,
        compensation_events,
        avg_step_latency_ms: avg,
        integrity_lines: kept.len() as u64,
        kept_events: kept,
    };

    (audit, findings)
}

fn make_finding(
    pv: &PolicyView,
    ftype: &str,
    saga_id: &str,
    event_id: Option<String>,
    step: Option<String>,
    evidence: serde_json::Value,
) -> Finding {
    let severity = pv
        .finding_severity
        .get(ftype)
        .cloned()
        .unwrap_or_else(|| "medium".to_string());
    let severity_rank = *pv.severity_ranks.get(&severity).unwrap_or(&99);
    Finding {
        finding_type: ftype.to_string(),
        severity,
        severity_rank,
        saga_id: saga_id.to_string(),
        event_id,
        step,
        evidence,
    }
}
