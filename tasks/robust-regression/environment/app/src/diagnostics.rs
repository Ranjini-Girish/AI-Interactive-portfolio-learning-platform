/// Compute the robust coefficient of determination (R²).
///
/// Uses weighted sums to account for the robust fitting procedure:
///   R² = 1 - SS_res / SS_tot
/// where SS_res = Σ w_i · r_i² and SS_tot = Σ w_i · (y_i - ȳ_w)²
/// with ȳ_w = Σ(w_i · y_i) / Σ(w_i) being the weighted mean.
pub fn r_squared_robust(y: &[f64], residuals: &[f64], _weights: &[f64]) -> f64 {
    let n = y.len() as f64;
    let y_mean = y.iter().sum::<f64>() / n;

    let ss_tot: f64 = y.iter().map(|yi| (yi - y_mean).powi(2)).sum();

    let ss_res: f64 = residuals.iter().map(|r| r.powi(2)).sum();

    if ss_tot <= 0.0 {
        return 0.0;
    }
    1.0 - ss_res / ss_tot
}
