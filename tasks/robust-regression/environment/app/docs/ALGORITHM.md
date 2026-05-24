# Algorithm Reference

## Huber M-Estimator

The Huber estimator minimizes:
```
Σ ρ(rᵢ / σ̂)
```
where ρ is the Huber loss:
```
ρ(u) = u²/2          if |u| ≤ k
ρ(u) = k|u| - k²/2   if |u| > k
```

The corresponding weight function (ψ'/u) is:
```
w(u) = 1       if |u| ≤ k
w(u) = k/|u|   if |u| > k
```

## MAD Scale Estimator

The Median Absolute Deviation is a robust scale estimator:
```
MAD = median(|xᵢ - median(x)|)
σ̂ = MAD × 1.4826
```

The factor 1.4826 ≈ 1/Φ⁻¹(3/4) makes it a consistent estimator
of σ for normally distributed data.

## Sandwich Covariance

For an M-estimator with weight function w, the asymptotic variance
of β̂ is estimated by the sandwich formula:

```
V(β̂) = (X'WX)⁻¹ (X'W²R²X) (X'WX)⁻¹
```

where W = diag(w₁, ..., wₙ) and R = diag(r₁, ..., rₙ).

The middle term ("meat") captures the empirical variance of the
estimating equations, while the outer terms ("bread") normalize
by the information matrix.

## Convergence Criterion

IRLS convergence uses relative parameter change:
```
Δ = max_j |βⱼ^(t+1) - βⱼ^(t)| / max(1, |βⱼ^(t)|)
```

The denominator max(1, |β|) prevents division by zero for
near-zero parameters while providing proper scaling for
parameters with large magnitudes.

## References

- Huber, P.J. (1964). "Robust Estimation of a Location Parameter"
- White, H. (1980). "A Heteroskedasticity-Consistent Covariance Matrix Estimator"
- Rousseeuw, P.J. and Croux, C. (1993). "Alternatives to the Median Absolute Deviation"
