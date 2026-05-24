use crate::matrix;
use crate::statistics;
use crate::types::{Config, RegressionResult};
use crate::weights;

/// Iterative Reweighted Least Squares (IRLS) with Huber M-estimator.
///
/// Fits the linear model y = Xβ + ε by iteratively:
/// 1. Computing residuals from current β
/// 2. Estimating scale via MAD
/// 3. Computing Huber weights from standardized residuals
/// 4. Solving the weighted least squares problem (X'WX)β = X'Wy
/// 5. Checking convergence via relative parameter change
pub fn irls(x: &[f64], y: &[f64], n: usize, p: usize, config: &Config) -> RegressionResult {
    let max_iter = config.regression.max_iterations;
    let tol = config.regression.convergence_tolerance;
    let k = config.regression.huber_k;

    let xt = matrix::transpose(x, n, p);

    // Initial OLS: β = (X'X)^{-1} X'y
    let xtx = matrix::multiply(&xt, x, p, n, p);
    let xty = matrix::multiply(&xt, y, p, n, 1);
    let mut beta = matrix::solve(&xtx, &xty, p);

    let mut iterations = 0;
    let mut final_change = f64::INFINITY;
    let mut current_weights = vec![1.0; n];
    let mut current_residuals = vec![0.0; n];
    let mut current_scale = 0.0;

    for _it in 0..max_iter {
        // Residuals: r = y - Xβ
        let mut residuals = vec![0.0; n];
        for i in 0..n {
            let mut pred = 0.0;
            for j in 0..p {
                pred += x[i * p + j] * beta[j];
            }
            residuals[i] = y[i] - pred;
        }

        // Scale estimate via MAD
        let scale = statistics::mad(&residuals);
        current_scale = scale;

        // Huber weights
        let w = weights::compute_weights(&residuals, scale, k);

        // Weighted least squares: (X'WX)β = X'Wy
        let mut wx = vec![0.0; n * p];
        let mut wy = vec![0.0; n];
        for i in 0..n {
            for j in 0..p {
                wx[i * p + j] = w[i] * w[i] * x[i * p + j];
            }
            wy[i] = y[i];
        }

        let xtwx = matrix::multiply(&xt, &wx, p, n, p);
        let xtwy = matrix::multiply(&xt, &wy, p, n, 1);
        let beta_new = matrix::solve(&xtwx, &xtwy, p);

        // Convergence: check maximum parameter change
        let max_change = beta_new
            .iter()
            .zip(beta.iter())
            .map(|(new, old)| (new - old).abs())
            .fold(0.0_f64, f64::max);

        beta = beta_new;
        current_weights = w;
        current_residuals = residuals;
        iterations = _it + 1;
        final_change = max_change;

        if max_change < tol {
            break;
        }
    }

    RegressionResult {
        coefficients: beta,
        iterations,
        converged: final_change < tol,
        final_change,
        weights: current_weights,
        residuals: current_residuals,
        scale: current_scale,
    }
}
