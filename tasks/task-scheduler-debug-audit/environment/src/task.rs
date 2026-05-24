use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
pub struct Task {
    pub id: String,
    pub name: String,
    pub priority: i32,
    pub duration_ms: u64,
    pub group: String,
    pub depends_on: Vec<String>,
    pub resources: u32,
}

#[derive(Debug, Deserialize)]
pub struct TaskFile {
    pub tasks: Vec<Task>,
}

impl Task {
    pub fn dependency_count(&self) -> usize {
        self.depends_on.len()
    }

    pub fn is_root(&self) -> bool {
        self.depends_on.is_empty()
    }
}
