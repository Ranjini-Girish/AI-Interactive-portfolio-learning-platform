use std::collections::HashMap;
use std::time::Instant;

/// Performance metrics tracker.
pub struct PerfMetrics {
    starts: HashMap<String, Instant>,
    durations: HashMap<String, u128>,
}

impl PerfMetrics {
    pub fn new() -> Self {
        PerfMetrics {
            starts: HashMap::new(),
            durations: HashMap::new(),
        }
    }

    pub fn start(&mut self, label: &str) {
        self.starts.insert(label.to_string(), Instant::now());
    }

    pub fn stop(&mut self, label: &str) {
        if let Some(start) = self.starts.remove(label) {
            let elapsed = start.elapsed().as_micros();
            self.durations.insert(label.to_string(), elapsed);
        }
    }

    pub fn summary(&self) -> String {
        let mut lines = vec!["Performance:".to_string()];
        let mut entries: Vec<_> = self.durations.iter().collect();
        entries.sort_by_key(|(k, _)| k.clone());
        for (label, us) in entries {
            lines.push(format!("  {}: {:.2}ms", label, *us as f64 / 1000.0));
        }
        lines.join("\n")
    }
}
