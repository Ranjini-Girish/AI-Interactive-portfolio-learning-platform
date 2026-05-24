/// Compute the median of a slice. The input is cloned and sorted internally.
pub fn median(values: &[f64]) -> f64 {
    let mut sorted: Vec<f64> = values.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let n = sorted.len();
    if n == 0 {
        return 0.0;
    }
    if n % 2 == 0 {
        (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0
    } else {
        sorted[n / 2]
    }
}

/// Median Absolute Deviation (MAD) with consistency factor 1.4826
/// for asymptotic normality. Measures spread as the median of
/// absolute deviations from the central tendency.
pub fn mad(values: &[f64]) -> f64 {
    let n = values.len() as f64;
    let center = values.iter().sum::<f64>() / n;
    let abs_devs: Vec<f64> = values.iter().map(|v| (v - center).abs()).collect();
    median(&abs_devs) * 1.4826
}
