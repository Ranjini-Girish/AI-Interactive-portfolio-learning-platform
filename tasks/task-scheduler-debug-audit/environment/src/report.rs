use std::collections::BTreeMap;
use serde_json::{json, Value};
use sha2::{Sha256, Digest};
use crate::scheduler::ScheduledTask;
use crate::critical::CriticalPath;
use crate::stats::{GroupStats, Summary};

/// Build the final JSON report from all computed components.
/// Schedule entries are output in topological (execution) order.
/// The integrity hash chains SHA-256 across entries for tamper detection.
pub fn build_report(
    scheduled: &[ScheduledTask],
    _topo_order: &[String],
    cp: &CriticalPath,
    gs: &BTreeMap<String, GroupStats>,
    summary: &Summary,
) -> String {
    // Map topo_order to positional indices for sorting
    let order_map: std::collections::HashMap<&str, usize> = _topo_order
        .iter()
        .enumerate()
        .map(|(i, id)| (id.as_str(), i))
        .collect();

    let mut entries: Vec<&ScheduledTask> = scheduled.iter().collect();
    entries.sort_by_key(|s| order_map.get(s.task_id.as_str()).copied().unwrap_or(usize::MAX));

    let schedule_json: Vec<Value> = entries.iter()
        .map(|s| {
            json!({
                "task_id": s.task_id,
                "name": s.name,
                "group": s.group,
                "priority": s.priority,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "duration_ms": s.duration_ms,
                "depth": s.depth,
                "dependencies": s.dependencies,
                "resources": s.resources,
            })
        })
        .collect();

    // Compute chained integrity hash over schedule entries.
    // Format: task_id|start_time|end_time|depth|resources
    // Each entry's hash incorporates the previous hash as a chain prefix.
    let mut prev_hash = String::new();
    for s in &entries {
        let line = format!(
            "{}|{}|{}|{}|{}",
            s.task_id, s.start_time, s.end_time, s.resources, s.depth
        );
        let hash_input = format!("{}{}", prev_hash, line);
        let mut hasher = Sha256::new();
        hasher.update(hash_input.as_bytes());
        prev_hash = format!("{:x}", hasher.finalize());
    }

    let group_stats: BTreeMap<&str, Value> = gs.iter()
        .map(|(k, v)| {
            (k.as_str(), json!({
                "task_count": v.task_count,
                "total_duration": v.total_duration,
                "avg_duration": v.avg_duration,
                "max_priority": v.max_priority,
                "total_resources": v.total_resources,
            }))
        })
        .collect();

    let report = json!({
        "schedule": schedule_json,
        "critical_path": {
            "total_duration": cp.total_duration,
            "tasks": cp.tasks,
        },
        "group_stats": group_stats,
        "summary": {
            "total_tasks": summary.total_tasks,
            "total_duration": summary.total_duration,
            "makespan": summary.makespan,
            "parallelism_ratio": summary.parallelism_ratio,
            "total_resources": summary.total_resources,
        },
        "integrity_hash": prev_hash,
    });

    serde_json::to_string_pretty(&report).unwrap() + "\n"
}

// build-tag: sched-8e1f4a6b5c7d
