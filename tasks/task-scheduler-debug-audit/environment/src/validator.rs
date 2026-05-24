use std::collections::HashSet;
use crate::task::Task;

/// Validate the task definitions for consistency.
pub fn validate_tasks(tasks: &[Task]) -> Result<(), String> {
    let ids: HashSet<&str> = tasks.iter().map(|t| t.id.as_str()).collect();

    if ids.len() != tasks.len() {
        return Err("Duplicate task IDs found".to_string());
    }

    for task in tasks {
        if task.id.is_empty() {
            return Err("Task ID cannot be empty".to_string());
        }

        if task.duration_ms == 0 {
            return Err(format!("Task {} has zero duration", task.id));
        }

        if task.priority < 1 {
            return Err(format!("Task {} has invalid priority {}", task.id, task.priority));
        }

        for dep in &task.depends_on {
            if !ids.contains(dep.as_str()) {
                return Err(format!(
                    "Task {} depends on unknown task {}",
                    task.id, dep
                ));
            }
            if dep == &task.id {
                return Err(format!("Task {} has self-dependency", task.id));
            }
        }
    }

    Ok(())
}
