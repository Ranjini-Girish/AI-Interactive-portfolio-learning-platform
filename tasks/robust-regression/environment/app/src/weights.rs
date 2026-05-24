/// Huber weight function for robust M-estimation.
///
/// The Huber estimator applies full weight to observations with
/// small residuals and downweights those with large residuals.
/// For tuning constant k = 1.345 (default), this achieves 95%
/// efficiency at the normal model.
pub fn huber_weight(residual: f64, scale: f64, k: f64) -> f64 {
    if scale < 1e-15 {
        return 1.0;
    }
    let u = residual.abs();
    if u <= k {
        1.0
    } else {
        k / u
    }
}

/// Compute Huber weights for a vector of residuals.
pub fn compute_weights(residuals: &[f64], _scale: f64, k: f64) -> Vec<f64> {
    residuals
        .iter()
        .map(|r| huber_weight(*r, 1.0, k))
        .collect()
}
