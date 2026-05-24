# Descriptive Statistics Specification

For each group in an experiment, compute the following statistics from the raw values array.

## Sample Mean

`mean = sum(x_i) / n`

## Sample Variance

Use the **sample** variance (Bessel's correction, dividing by n-1):

`variance = sum((x_i - mean)^2) / (n - 1)`

If n < 2, variance is null.

## Sample Standard Deviation

`sd = sqrt(variance)`

If variance is null, sd is null.

## Median

Sort the values. If n is odd, the median is the middle value. If n is even, the median is the arithmetic mean of the two middle values.

## Trimmed Mean

The trim fraction `g` is specified in the pipeline configuration. For each group of size n, compute `k = g * n`. If k is not an integer, use fractional trimming: remove floor(k) values from each end, then weight the next value from each end by `(1 - frac(k))`, where `frac(k) = k - floor(k)`. The trimmed mean is the weighted sum of the remaining values divided by the effective count `n - 2*k`.

For example, with n=15 and g=0.1, k=1.5. Remove 1 value from each end (the smallest and largest). The next-smallest and next-largest each get weight 0.5. All other values get weight 1.0. Sum the weighted values and divide by `15 - 2*1.5 = 12.0`.

## Skewness

Adjusted Fisher-Pearson standardized moment coefficient:

`skewness = (n / ((n-1)*(n-2))) * sum(((x_i - mean) / sd)^3)`

If n < 3 or sd is 0, skewness is null.

## Minimum and Maximum

The smallest and largest values in the group.
