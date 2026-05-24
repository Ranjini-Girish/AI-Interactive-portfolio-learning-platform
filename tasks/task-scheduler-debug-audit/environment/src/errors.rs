use std::fmt;

/// Error types for the scheduler.
#[derive(Debug)]
#[allow(dead_code)]
pub enum SchedulerError {
    InvalidInput(String),
    CycleDetected(Vec<String>),
    MissingDependency { task: String, dependency: String },
    IoError(std::io::Error),
}

impl fmt::Display for SchedulerError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SchedulerError::InvalidInput(msg) => write!(f, "Invalid input: {}", msg),
            SchedulerError::CycleDetected(nodes) => {
                write!(f, "Cycle detected involving: {}", nodes.join(", "))
            }
            SchedulerError::MissingDependency { task, dependency } => {
                write!(f, "Task {} depends on missing task {}", task, dependency)
            }
            SchedulerError::IoError(e) => write!(f, "IO error: {}", e),
        }
    }
}

impl From<std::io::Error> for SchedulerError {
    fn from(e: std::io::Error) -> Self {
        SchedulerError::IoError(e)
    }
}
