# Effect Size Specification

For each pairwise comparison, compute Hedges' g as the effect size measure.

## Cohen's d (intermediate)

`d = (mean_1 - mean_2) / s_pooled`

where the pooled standard deviation uses:

`s_pooled = sqrt(((n1-1)*s1^2 + (n2-1)*s2^2) / (n1 + n2 - 2))`

## Hedges' g correction

Hedges' g applies a small-sample correction factor J to Cohen's d:

`g = d * J`

where:

`J = 1 - 3 / (4 * (n1 + n2 - 2) - 1)`

This correction reduces bias for small sample sizes.

## Edge Cases

If the pooled standard deviation is 0 (both groups have zero variance), Hedges' g is null if the means are equal, and null if they differ (undefined).

If either group has n < 2, Hedges' g is null.
