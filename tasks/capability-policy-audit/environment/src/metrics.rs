pub fn avg_effective_arithmetic(values: &[i64]) -> f64 {
    let positive: Vec<i64> = values.iter().copied().filter(|v| *v > 0).collect();
    if positive.is_empty() {
        return 0.0;
    }
    let sum: i64 = positive.iter().sum();
    let avg = sum as f64 / positive.len() as f64;
    (avg * 10_000.0).round() / 10_000.0
}

pub fn harmonic_mean(values: &[f64]) -> f64 {
    let positive: Vec<f64> = values.iter().copied().filter(|v| *v > 0.0).collect();
    if positive.is_empty() {
        return 0.0;
    }
    let sum: f64 = positive.iter().map(|v| 1.0 / v).sum();
    let h = positive.len() as f64 / sum;
    (h * 10_000.0).round() / 10_000.0
}
