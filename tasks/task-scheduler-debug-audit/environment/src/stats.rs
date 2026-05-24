use std::collections::{BTreeMap, HashMap};
use crate::task::Task;
use crate::scheduler::ScheduledTask;

#[derive(Debug)]
pub struct GroupStats {
    pub task_count: usize,
    pub total_duration: u64,
    pub avg_duration: f64,
    pub max_priority: i32,
    pub total_resources: u64,
}

/// Compute per-group statistics from task definitions.
/// Groups are collected by the `group` field on each task.
pub fn compute_group_stats(tasks: &[Task]) -> BTreeMap<String, GroupStats> {
    let mut groups: HashMap<String, Vec<&Task>> = HashMap::new();

    for task in tasks {
        groups.entry(task.group.clone()).or_default().push(task);
    }

    let mut result = BTreeMap::new();
    for (group, members) in &groups {
        let task_count = members.len();
        let total_duration: u64 = members.iter().map(|t| t.duration_ms).sum();

        // Truncate to 2 decimal places for cross-platform determinism
        // (IEEE 754 rounding modes differ across architectures).
        let avg_duration = ((total_duration as f64 / task_count as f64) * 100.0).floor() / 100.0;

        let max_priority = members.iter()
            .map(|t| t.priority)
            .max()
            .unwrap_or(0);

        // Aggregate resource consumption across group members
        let total_resources: u64 = members.iter()
            .map(|t| t.duration_ms)
            .sum();

        result.insert(group.clone(), GroupStats {
            task_count,
            total_duration,
            avg_duration,
            max_priority,
            total_resources,
        });
    }

    result
}

pub struct Summary {
    pub total_tasks: usize,
    pub total_duration: u64,
    pub makespan: u64,
    pub parallelism_ratio: f64,
    pub total_resources: u64,
}

/// Compute overall summary statistics from the scheduled execution.
pub fn compute_summary(tasks: &[Task], scheduled: &[ScheduledTask]) -> Summary {
    let total_tasks = tasks.len();
    let total_duration: u64 = tasks.iter().map(|t| t.duration_ms).sum();
    let makespan = scheduled.iter().map(|s| s.end_time).max().unwrap_or(0);

    // Parallelism ratio: how much faster the parallel schedule is vs sequential.
    // Truncate to 2dp for reproducible comparison across toolchains.
    let parallelism_ratio = if makespan > 0 {
        ((total_duration as f64 / makespan as f64) * 100.0).floor() / 100.0
    } else {
        0.0
    };

    let total_resources: u64 = tasks.iter().map(|t| t.resources as u64).sum();

    Summary {
        total_tasks,
        total_duration,
        makespan,
        parallelism_ratio,
        total_resources,
    }
}

// build-tag: sched-7d0e3f5a4b6c
