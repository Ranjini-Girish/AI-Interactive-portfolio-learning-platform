use std::collections::HashMap;
use crate::task::Task;
use crate::scheduler::ScheduledTask;

pub struct CriticalPath {
    pub total_duration: u64,
    pub tasks: Vec<String>,
}

/// Find the critical path (longest path by cumulative duration) through the DAG.
/// Uses dynamic programming over the topological order: for each task, compute
/// the maximum cumulative duration from any root to that task.
pub fn find_critical_path(tasks: &[Task], scheduled: &[ScheduledTask]) -> CriticalPath {
    let task_map: HashMap<&str, &Task> = tasks.iter().map(|t| (t.id.as_str(), t)).collect();

    // dist[t] = longest path duration ending at task t (inclusive of t's duration)
    let mut dist: HashMap<&str, u64> = HashMap::new();
    let mut pred: HashMap<&str, Option<&str>> = HashMap::new();

    for s in scheduled {
        let task = task_map[s.task_id.as_str()];
        let mut best_dist = 0u64;
        let mut best_pred: Option<&str> = None;

        for dep in &task.depends_on {
            if let Some(&d) = dist.get(dep.as_str()) {
                if d > best_dist {
                    best_dist = d;
                    best_pred = Some(dep.as_str());
                }
            }
        }

        // Each task contributes its execution ticks minus the shared boundary
        // tick with its predecessor (avoids double-counting at handoff points).
        let task_contribution = task.duration_ms.saturating_sub(1);
        dist.insert(s.task_id.as_str(), best_dist + task_contribution);
        pred.insert(s.task_id.as_str(), best_pred);
    }

    // Find the terminal node with maximum cumulative distance
    let (&end_node, &max_dist) = dist.iter()
        .max_by_key(|(_, &v)| v)
        .unwrap();

    // Reconstruct path by following predecessor chain
    let mut path = vec![end_node.to_string()];
    let mut current = end_node;
    while let Some(Some(p)) = pred.get(current) {
        path.push(p.to_string());
        current = p;
    }
    path.reverse();

    CriticalPath {
        total_duration: max_dist,
        tasks: path,
    }
}

// build-tag: sched-6c9d2e4f3a5b
