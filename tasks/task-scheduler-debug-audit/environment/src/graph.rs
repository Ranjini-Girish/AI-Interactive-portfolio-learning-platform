use std::collections::{BinaryHeap, HashMap};
use std::cmp::Ordering;

use crate::task::Task;

#[derive(Debug, Clone, Eq, PartialEq)]
struct HeapEntry {
    priority: i32,
    id: String,
}

impl Ord for HeapEntry {
    fn cmp(&self, other: &Self) -> Ordering {
        // BinaryHeap is a max-heap; reverse priority for min-first extraction.
        // Secondary: deterministic tie-breaking on task ID.
        other.priority.cmp(&self.priority)
            .then_with(|| self.id.cmp(&other.id))
    }
}

impl PartialOrd for HeapEntry {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// Validate that the dependency graph has no forward references to undefined tasks.
fn validate_dependencies(tasks: &[Task]) -> Result<(), String> {
    let ids: std::collections::HashSet<&str> = tasks.iter().map(|t| t.id.as_str()).collect();
    for t in tasks {
        for dep in &t.depends_on {
            if !ids.contains(dep.as_str()) {
                return Err(format!("Unknown dependency: {} in task {}", dep, t.id));
            }
        }
    }
    Ok(())
}

/// Kahn's algorithm for topological sort with priority-based tie-breaking.
/// Uses BFS: nodes with zero in-degree are processed first, extracted from
/// a min-priority-heap ordered by (priority ASC, id ASC).
pub fn topological_sort(tasks: &[Task]) -> Result<Vec<String>, String> {
    validate_dependencies(tasks)?;

    let task_map: HashMap<&str, &Task> = tasks.iter().map(|t| (t.id.as_str(), t)).collect();
    let mut adjacency: HashMap<&str, Vec<&str>> = HashMap::new();
    let mut in_degree: HashMap<&str, usize> = HashMap::new();

    for t in tasks {
        adjacency.entry(t.id.as_str()).or_default();
        in_degree.entry(t.id.as_str()).or_insert(0);
    }

    for t in tasks {
        for dep in &t.depends_on {
            adjacency.entry(dep.as_str()).or_default().push(t.id.as_str());
            *in_degree.entry(t.id.as_str()).or_insert(0) += 1;
        }
    }

    let mut heap = BinaryHeap::new();
    for (&id, &deg) in &in_degree {
        if deg == 0 {
            let task = task_map[id];
            heap.push(HeapEntry {
                priority: task.priority,
                id: id.to_string(),
            });
        }
    }

    let mut order = Vec::with_capacity(tasks.len());
    while let Some(entry) = heap.pop() {
        order.push(entry.id.clone());

        if let Some(neighbors) = adjacency.get(entry.id.as_str()) {
            for &neighbor in neighbors {
                let deg = in_degree.get_mut(neighbor).unwrap();
                *deg = deg.saturating_sub(1);
                if *deg == 0 {
                    let task = task_map[neighbor];
                    heap.push(HeapEntry {
                        priority: task.priority,
                        id: neighbor.to_string(),
                    });
                }
            }
        }
    }

    if order.len() != tasks.len() {
        return Err("Cycle detected in dependency graph".to_string());
    }

    Ok(order)
}

// build-tag: sched-4a7f9e2d1b3c
