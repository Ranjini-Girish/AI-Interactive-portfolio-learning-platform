pub fn arithmetic_mean(vals: &[f64]) -> f64 {
    if vals.is_empty() {
        return 0.0;
    }
    let s: f64 = vals.iter().sum();
    (s / vals.len() as f64 * 1_000_000.0).round() / 1_000_000.0
}

pub fn harmonic_mean(vals: &[f64]) -> f64 {
    let pos: Vec<f64> = vals.iter().copied().filter(|v| *v > 0.0).collect();
    if pos.is_empty() {
        return 0.0;
    }
    let n = pos.len() as f64;
    let denom: f64 = pos.iter().map(|v| 1.0 / v).sum();
    ((n / denom) * 1_000_000.0).round() / 1_000_000.0
}
