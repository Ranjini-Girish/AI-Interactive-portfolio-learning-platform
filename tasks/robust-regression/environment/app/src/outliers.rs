/// Detect outliers based on standardized residuals exceeding a threshold.
///
/// An observation i is flagged as an outlier if |r_i| / scale > threshold,
/// implementing two-sided rejection for both positive and negative deviations.
pub fn detect(residuals: &[f64], scale: f64, threshold: f64) -> Vec<usize> {
    if scale < 1e-15 {
        return Vec::new();
    }
    residuals
        .iter()
        .enumerate()
        .filter(|(_, r)| **r / scale > threshold)
        .map(|(i, _)| i)
        .collect()
}
