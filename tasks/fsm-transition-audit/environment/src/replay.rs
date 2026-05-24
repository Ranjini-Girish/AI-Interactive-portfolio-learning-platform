use crate::metrics;
use serde::Deserialize;
use std::collections::{BTreeMap, HashSet};

#[derive(Debug, Clone, Deserialize)]
pub struct Transition {
    pub transition_id: String,
    pub sequence: u64,
    pub logged_at: u64,
    pub from_state: String,
    pub to_state: String,
    pub duration_ms: Option<u64>,
}

#[derive(Debug, Deserialize)]
pub struct WorkflowFile {
    pub workflow_id: String,
    pub fsm_id: String,
    pub transitions: Vec<Transition>,
}

#[derive(Debug, Deserialize)]
pub struct FsmDef {
    pub fsm_id: String,
    pub initial_state: String,
    pub terminal_states: Vec<String>,
    pub allowed_edges: Vec<Vec<String>>,
}

#[derive(Debug, Clone)]
pub struct PolicyView {
    pub finding_severity: BTreeMap<String, String>,
    pub severity_ranks: BTreeMap<String, i64>,
}

#[derive(Debug, Clone)]
pub struct WorkflowAudit {
    pub workflow_id: String,
    pub fsm_id: String,
    pub transitions_kept: u64,
    pub transitions_skipped: u64,
    pub final_state: String,
    pub states_visited: u64,
    pub avg_dwell_ms: f64,
    pub integrity_lines: u64,
    pub kept_transitions: Vec<Transition>,
}

#[derive(Debug, Clone)]
pub struct Finding {
    pub finding_type: String,
    pub severity: String,
    pub severity_rank: i64,
    pub workflow_id: String,
    pub transition_id: Option<String>,
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

fn sort_transitions(events: &mut [Transition]) {
    events.sort_by(|a, b| a.logged_at.cmp(&b.logged_at));
}

fn edge_allowed(fsm: &FsmDef, from: &str, to: &str) -> bool {
    fsm.allowed_edges
        .iter()
        .any(|e| e.len() == 2 && e[0] == from && e[1] == to)
}

pub fn replay_workflow(
    wf: &WorkflowFile,
    fsm: &FsmDef,
    policy: &super::Policy,
) -> (WorkflowAudit, Vec<Finding>) {
    let pv = PolicyView::from_policy(policy);
    let mut transitions = wf.transitions.clone();
    sort_transitions(&mut transitions);

    let terminals: HashSet<String> = fsm.terminal_states.iter().cloned().collect();
    let mut findings = Vec::new();
    let mut kept: Vec<Transition> = Vec::new();
    let mut seen_ids: HashSet<String> = HashSet::new();
    let mut skipped = 0u64;
    let mut current = fsm.initial_state.clone();

    for tr in transitions {
        if seen_ids.contains(&tr.transition_id) {
            skipped += 1;
            findings.push(make_finding(
                &pv,
                "duplicate_transition_skipped",
                &wf.workflow_id,
                Some(tr.transition_id.clone()),
                serde_json::json!({"duplicate_sequence": tr.sequence}),
            ));
            continue;
        }
        seen_ids.insert(tr.transition_id.clone());

        if tr.from_state != current {
            findings.push(make_finding(
                &pv,
                "state_mismatch",
                &wf.workflow_id,
                Some(tr.transition_id.clone()),
                serde_json::json!({
                    "expected_state": current,
                    "from_state": tr.from_state
                }),
            ));
        } else if !edge_allowed(fsm, &current, &tr.to_state) {
            findings.push(make_finding(
                &pv,
                "illegal_transition",
                &wf.workflow_id,
                Some(tr.transition_id.clone()),
                serde_json::json!({
                    "from_state": current,
                    "to_state": tr.to_state
                }),
            ));
        } else if terminals.contains(&current) {
            findings.push(make_finding(
                &pv,
                "terminal_reopened",
                &wf.workflow_id,
                Some(tr.transition_id.clone()),
                serde_json::json!({
                    "terminal_state": current,
                    "to_state": tr.to_state
                }),
            ));
        }

        kept.push(tr.clone());
        current = tr.to_state.clone();
    }

    for i in 1..kept.len() {
        if kept[i].logged_at < kept[i - 1].logged_at {
            findings.push(make_finding(
                &pv,
                "timestamp_regression",
                &wf.workflow_id,
                Some(kept[i].transition_id.clone()),
                serde_json::json!({
                    "previous_logged_at": kept[i - 1].logged_at,
                    "logged_at": kept[i].logged_at
                }),
            ));
        }
    }

    if !terminals.contains(&current) {
        findings.push(make_finding(
            &pv,
            "stuck_workflow",
            &wf.workflow_id,
            None,
            serde_json::json!({"final_state": current}),
        ));
    }

    let mut visited: HashSet<String> = HashSet::new();
    visited.insert(fsm.initial_state.clone());
    for tr in &kept {
        visited.insert(tr.to_state.clone());
    }

    let avg = metrics::avg_dwell_arithmetic(&kept);

    let audit = WorkflowAudit {
        workflow_id: wf.workflow_id.clone(),
        fsm_id: wf.fsm_id.clone(),
        transitions_kept: kept.len() as u64,
        transitions_skipped: skipped,
        final_state: current,
        states_visited: visited.len() as u64,
        avg_dwell_ms: avg,
        integrity_lines: kept.len() as u64,
        kept_transitions: kept,
    };

    (audit, findings)
}

fn make_finding(
    pv: &PolicyView,
    ftype: &str,
    workflow_id: &str,
    transition_id: Option<String>,
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
        workflow_id: workflow_id.to_string(),
        transition_id,
        evidence,
    }
}
