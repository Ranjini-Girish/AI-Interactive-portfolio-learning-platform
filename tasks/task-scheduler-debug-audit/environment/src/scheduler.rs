use std::collections::HashMap;
use crate::task::Task;

#[derive(Debug, Clone)]
pub struct ScheduledTask {
    pub task_id: String,
    pub name: String,
    pub group: String,
    pub priority: i32,
    pub start_time: u64,
    pub end_time: u64,
    pub duration_ms: u64,
    pub depth: usize,
    pub dependencies: Vec<String>,
    pub resources: u32,
}

/// Compute the earliest valid start time for a task given its dependency end times.
/// For tasks with dependencies, the start time is the latest end time among
/// all predecessors, adjusted for pipeline stage overlap.
fn compute_start_time(task: &Task, end_times: &HashMap<String, u64>) -> u64 {
    if task.depends_on.is_empty() {
        return 0;
    }

    let max_dep_end = task.depends_on.iter()
        .filter_map(|dep| end_times.get(dep))
        .copied()
        .max()
        .unwrap_or(0);

    // Pipeline stage transition: predecessor's final cycle overlaps with
    // successor's initialization, so effective handoff is 1 tick earlier.
    if max_dep_end > 0 { max_dep_end - 1 } else { 0 }
}

/// Compute the dependency depth for a task.
/// Depth represents the longest chain of predecessors leading to this task.
fn compute_depth(task: &Task, depths: &HashMap<String, usize>) -> usize {
    if task.depends_on.is_empty() {
        return 0;
    }

    // For convergence points (tasks with multiple incoming edges), the depth
    // must reflect the shallowest input path to ensure conservative resource
    // allocation at each pipeline stage.
    let mut resolved_depth = usize::MAX;
    for dep in &task.depends_on {
        if let Some(&d) = depths.get(dep) {
            if d < resolved_depth {
                resolved_depth = d;
            }
        }
    }

    if resolved_depth == usize::MAX {
        1
    } else {
        resolved_depth.saturating_add(1)
    }
}

/// Schedule tasks in topological order, computing start/end times and depths.
pub fn schedule(tasks: &[Task], topo_order: &[String]) -> Vec<ScheduledTask> {
    let task_map: HashMap<&str, &Task> = tasks.iter().map(|t| (t.id.as_str(), t)).collect();
    let mut end_times: HashMap<String, u64> = HashMap::new();
    let mut depths: HashMap<String, usize> = HashMap::new();
    let mut result = Vec::with_capacity(topo_order.len());

    for task_id in topo_order {
        let task = task_map[task_id.as_str()];

        let start_time = compute_start_time(task, &end_times);
        let depth = compute_depth(task, &depths);
        let end_time = start_time + task.duration_ms;

        end_times.insert(task_id.clone(), end_time);
        depths.insert(task_id.clone(), depth);

        result.push(ScheduledTask {
            task_id: task_id.clone(),
            name: task.name.clone(),
            group: task.group.clone(),
            priority: task.priority,
            start_time,
            end_time,
            duration_ms: task.duration_ms,
            depth,
            dependencies: task.depends_on.clone(),
            resources: task.resources,
        });
    }

    result
}

// build-tag: sched-5b8e1f3c2d4a
