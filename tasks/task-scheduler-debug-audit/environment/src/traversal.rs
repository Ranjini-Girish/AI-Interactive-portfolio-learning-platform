use std::collections::{HashMap, HashSet, VecDeque};
use crate::task::Task;

/// Compute the set of all ancestors for each task.
#[allow(dead_code)]
pub fn compute_ancestors(tasks: &[Task]) -> HashMap<String, HashSet<String>> {
    let mut ancestors: HashMap<String, HashSet<String>> = HashMap::new();

    let dep_map: HashMap<&str, &[String]> = tasks.iter()
        .map(|t| (t.id.as_str(), t.depends_on.as_slice()))
        .collect();

    for task in tasks {
        let mut visited = HashSet::new();
        let mut queue = VecDeque::new();

        for dep in &task.depends_on {
            queue.push_back(dep.as_str());
        }

        while let Some(node) = queue.pop_front() {
            if visited.insert(node.to_string()) {
                if let Some(deps) = dep_map.get(node) {
                    for d in *deps {
                        queue.push_back(d.as_str());
                    }
                }
            }
        }

        ancestors.insert(task.id.clone(), visited);
    }

    ancestors
}

/// Find all leaf nodes (tasks with no dependents).
#[allow(dead_code)]
pub fn find_leaves(tasks: &[Task]) -> Vec<String> {
    let all_deps: HashSet<&str> = tasks.iter()
        .flat_map(|t| t.depends_on.iter().map(|d| d.as_str()))
        .collect();

    let depended_on: HashSet<&str> = tasks.iter()
        .filter(|t| all_deps.contains(t.id.as_str()))
        .map(|t| t.id.as_str())
        .collect();

    tasks.iter()
        .filter(|t| !depended_on.contains(t.id.as_str()))
        .map(|t| t.id.clone())
        .collect()
}
