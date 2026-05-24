# Rounding Rules

All floating-point results are rounded to the number of decimal places specified by `rounding_decimals` in the pipeline configuration. The rounding method is round-half-away-from-zero (standard mathematical rounding).

Rounding is applied to the final output values only. Intermediate computations should use full floating-point precision to avoid accumulation of rounding errors.

Specifically, round these fields: mean, trimmed_mean, median, variance, sd, mad, mad_scaled, skewness, outlier_modified_z values, t_statistic, welch_df, p_value, hedges_g, ci_lower, ci_upper, and correlation matrix entries.

Integer fields (n, outlier_indices, counts) are never rounded.

Null values remain null and are not rounded.
