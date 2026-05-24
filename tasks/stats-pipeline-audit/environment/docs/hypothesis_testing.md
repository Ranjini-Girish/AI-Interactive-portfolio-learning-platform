# Hypothesis Testing Specification

For each pair of groups within an experiment, perform a two-tailed Welch's t-test.

## Welch's t-statistic

`t = (mean_1 - mean_2) / sqrt(s1^2/n1 + s2^2/n2)`

where s1^2 and s2^2 are the sample variances (with Bessel's correction) and n1, n2 are the sample sizes.

## Welch-Satterthwaite Degrees of Freedom

The degrees of freedom is computed using the Welch-Satterthwaite equation:

`df = (s1^2/n1 + s2^2/n2)^2 / ((s1^2/n1)^2/(n1-1) + (s2^2/n2)^2/(n2-1))`

This value is generally not an integer. Report it as a floating-point number without rounding to an integer.

## P-value

The two-tailed p-value is computed from the t-distribution CDF:

`p = 2 * (1 - T_cdf(|t|, df))`

where T_cdf is the cumulative distribution function of the t-distribution with `df` degrees of freedom.

The t-distribution CDF is computed using the regularized incomplete beta function:

`T_cdf(t, df) = 1 - 0.5 * I_x(df/2, 1/2)`

where `x = df / (df + t^2)` and `I_x(a, b)` is the regularized incomplete beta function.

The regularized incomplete beta function is evaluated using the continued fraction expansion (Lentz's method):

`I_x(a, b) = (x^a * (1-x)^b) / (a * B(a,b)) * CF(x, a, b)`

where B(a,b) is the beta function and CF is the continued fraction. Use the standard DLMF 8.17.22 continued fraction with at least 200 iterations and convergence tolerance of 1e-12.

## Significance

A comparison is significant if `p < significance_alpha` from the pipeline configuration.

## Edge Cases

If either group has n < 2 (variance undefined), the comparison cannot be performed. Report t_statistic, df, p_value, and significant as null.

If both groups have zero variance (sd = 0), and their means are equal, t = 0, p = 1.0. If means differ and sd = 0, the t-statistic is undefined; report as null.

## Pair Ordering

Comparisons are generated for all unordered pairs of groups within an experiment. The pairs are sorted lexicographically by (group_a, group_b) where group_a < group_b alphabetically.
