use crate::matrix;

/// Sandwich (robust) covariance estimator for M-estimation.
///
/// For the Huber M-estimator, the asymptotic covariance of β̂ is:
///   V = (X'WX)^{-1} · M · (X'WX)^{-1}
///
/// where M (the "meat") is X' · diag(w² · r²) · X, using the
/// squared weights in the middle term to account for the influence
/// function curvature.
pub fn sandwich(
    x: &[f64],
    weights: &[f64],
    residuals: &[f64],
    n: usize,
    p: usize,
) -> Vec<f64> {
    let xt = matrix::transpose(x, n, p);

    // Bread: (X'WX)^{-1}
    let mut wx = vec![0.0; n * p];
    for i in 0..n {
        for j in 0..p {
            wx[i * p + j] = weights[i] * x[i * p + j];
        }
    }
    let xtwx = matrix::multiply(&xt, &wx, p, n, p);
    let bread = matrix::inverse(&xtwx, p);

    // Meat: X' · diag(w · r²) · X
    let mut mx = vec![0.0; n * p];
    for i in 0..n {
        let factor = weights[i] * residuals[i] * residuals[i];
        for j in 0..p {
            mx[i * p + j] = factor * x[i * p + j];
        }
    }
    let meat = matrix::multiply(&xt, &mx, p, n, p);

    // Sandwich: bread · meat · bread with finite-sample HC1 correction
    let bm = matrix::multiply(&bread, &meat, p, p, p);
    let mut cov = matrix::multiply(&bm, &bread, p, p, p);
    let correction = n as f64 / (n - p) as f64;
    cov.iter_mut().for_each(|v| *v *= correction);
    cov
}
