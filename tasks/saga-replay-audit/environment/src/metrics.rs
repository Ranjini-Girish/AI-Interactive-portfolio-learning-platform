use crate::replay::SagaEvent;

pub fn avg_latency_arithmetic(events: &[SagaEvent]) -> f64 {
    let mut sum = 0u64;
    let mut n = 0u64;
    for ev in events {
        if ev.status == "completed" {
            if let Some(d) = ev.duration_ms {
                if d > 0 {
                    sum += d;
                    n += 1;
                }
            }
        }
    }
    if n == 0 {
        return 0.0;
    }
    let avg = sum as f64 / n as f64;
    (avg * 1_000_000.0).round() / 1_000_000.0
}

pub fn harmonic_mean(values: &[f64]) -> f64 {
    let positive: Vec<f64> = values.iter().copied().filter(|v| *v > 0.0).collect();
    if positive.is_empty() {
        return 0.0;
    }
    let sum: f64 = positive.iter().map(|v| 1.0 / v).sum();
    let h = positive.len() as f64 / sum;
    (h * 1_000_000.0).round() / 1_000_000.0
}
