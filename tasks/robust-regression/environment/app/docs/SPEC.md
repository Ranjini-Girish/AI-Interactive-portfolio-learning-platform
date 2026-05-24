# Robust Regression Pipeline — Specification

## Overview

This pipeline fits a linear model `y = Xβ + ε` to sensor data using
Iterative Reweighted Least Squares (IRLS) with the Huber M-estimator.
It produces robust parameter estimates, confidence intervals via the
sandwich covariance estimator, and flags statistical outliers.

## Input

- **Data**: CSV file at `/app/data/sensors.csv` with header row.
  Columns specified in the config as predictors and response.
- **Config**: TOML file at `/app/config/analysis.toml`.

## Algorithm

### 1. Design Matrix Construction

The design matrix `X` is `n × p` where `p = (number of predictors) + 1`.
Column 0 is the intercept (all 1s). Subsequent columns correspond to the
predictors in the order listed in the config.

### 2. Initial OLS Fit

Compute the ordinary least squares estimate:
```
β₀ = (X'X)⁻¹ X'y
```

### 3. IRLS Iteration

For each iteration t = 1, 2, ..., max_iterations:

1. **Residuals**: `r = y - Xβ`

2. **Scale estimate**: Compute the Median Absolute Deviation (MAD):
   ```
   σ̂ = 1.4826 · median(|rᵢ - median(r)|)
   ```
   Note: The MAD is computed as deviations from the **median** of the
   residuals, NOT the mean. The constant 1.4826 is the exact consistency
   factor for the normal distribution: `1 / Φ⁻¹(3/4)`.

3. **Huber weights**: For tuning constant `k` (default 1.345):
   ```
   uᵢ = |rᵢ| / σ̂      (standardized residual)
   wᵢ = 1              if uᵢ ≤ k
   wᵢ = k / uᵢ         if uᵢ > k
   ```
   The weight function operates on the **standardized** residual `|r|/σ̂`,
   not the raw residual `|r|`. This normalization ensures the threshold
   adapts to the current scale of the data.

4. **Weighted least squares**: Solve `(X'WX)β = X'Wy` where `W = diag(w)`.

5. **Convergence check**: The algorithm converges when the **relative**
   change in parameters falls below the tolerance:
   ```
   max_j |β_new[j] - β_old[j]| / max(1, |β_old[j]|) < tolerance
   ```
   This relative criterion (dividing by `max(1, |β_old|)`) ensures
   convergence is scale-invariant across parameters of different magnitudes.

After convergence (or reaching max_iterations), recompute final residuals,
scale, and weights using the converged β.

### 4. Sandwich Covariance Estimator

The robust covariance of β̂ uses the sandwich form:
```
V = B · M · B
```
where:
- **Bread**: `B = (X'WX)⁻¹`
- **Meat**: `M = X' · diag(w² · r²) · X`

The meat term uses **w²** (weights squared), not w. This is because the
sandwich estimator for M-estimators requires the square of the weight
function in the influence function's variance:
```
M_ij = Σₖ wₖ² · rₖ² · xₖᵢ · xₖⱼ
```

Standard errors are `SE[j] = √(V[j,j])`.

### 5. Outlier Detection

An observation is classified as an outlier using **two-sided** rejection:
```
|rᵢ| / σ̂ > threshold
```
Both positive and negative deviations beyond the threshold are flagged.
The test is on the absolute standardized residual.

### 6. Robust R²

The robust coefficient of determination uses the final IRLS weights:
```
ȳ_w = Σ(wᵢ · yᵢ) / Σ(wᵢ)
SS_tot = Σ wᵢ · (yᵢ - ȳ_w)²
SS_res = Σ wᵢ · rᵢ²
R² = 1 - SS_res / SS_tot
```
Both sums use the weights from the final IRLS iteration. The weighted
mean `ȳ_w` is used (not the unweighted mean).

## Output

JSON file at `/app/output/analysis.json` with structure:

```json
{
  "coefficients": [
    {"name": "...", "value": ..., "std_error": ...}
  ],
  "convergence": {
    "iterations": ...,
    "converged": true/false,
    "final_change": ...
  },
  "outliers": {
    "indices": [...],
    "count": ...,
    "threshold": ...
  },
  "diagnostics": {
    "scale_estimate": ...,
    "r_squared_robust": ...,
    "degrees_of_freedom": ...
  }
}
```

### Coefficient ordering

Coefficients are sorted by **absolute value descending**. For coefficients
with equal absolute value after rounding, sort by name ascending
(lexicographic).

### Numeric precision

All floating-point values in the output are rounded to `precision`
decimal places (configured in `[output]` section, default 6).

### Degrees of freedom

`degrees_of_freedom = n - p` where n is the number of observations and
p is the number of parameters (including intercept).
