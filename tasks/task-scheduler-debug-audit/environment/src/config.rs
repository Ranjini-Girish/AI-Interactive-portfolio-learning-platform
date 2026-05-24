/// Scheduler configuration parameters.
#[derive(Debug, Clone)]
pub struct SchedulerConfig {
    pub max_parallelism: usize,
    pub timeout_ms: u64,
    pub enable_caching: bool,
    pub sort_stable: bool,
}

impl Default for SchedulerConfig {
    fn default() -> Self {
        SchedulerConfig {
            max_parallelism: 4,
            timeout_ms: 30000,
            enable_caching: true,
            sort_stable: true,
        }
    }
}

impl SchedulerConfig {
    #[allow(dead_code)]
    pub fn with_parallelism(mut self, n: usize) -> Self {
        self.max_parallelism = n;
        self
    }

    #[allow(dead_code)]
    pub fn with_timeout(mut self, ms: u64) -> Self {
        self.timeout_ms = ms;
        self
    }
}
