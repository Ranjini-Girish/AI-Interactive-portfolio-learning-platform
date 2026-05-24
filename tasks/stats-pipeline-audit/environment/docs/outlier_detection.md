# Outlier Detection Specification

Outliers are detected using the Modified Z-Score method based on the Median Absolute Deviation (MAD).

## MAD Computation

1. Compute the median of the group values.
2. Compute the absolute deviations: `|x_i - median|` for each value.
3. The MAD is the median of these absolute deviations.
4. The scaled MAD is: `mad_scaled = 1.4826 * MAD`

The scaling constant 1.4826 makes the MAD a consistent estimator of the standard deviation for normally distributed data.

## Modified Z-Score

For each value x_i:

`modified_z = 0.6745 * (x_i - median) / MAD`

Note: the numerator uses the unscaled MAD (not the scaled version). The constant 0.6745 is the 75th percentile of the standard normal distribution.

Equivalently: `modified_z = (x_i - median) / mad_scaled`

## Outlier Classification

A value is classified as an outlier if `|modified_z| > threshold`, where the threshold is specified in the pipeline configuration (`outlier_threshold`).

## Edge Cases

If MAD is 0 (all values are identical, or all deviations from the median are 0), the modified Z-score is 0 for values equal to the median and null for values not equal to the median. In practice, if MAD is 0, no outliers are detected (all modified Z-scores are reported as 0).

## Output

For each group, report the list of outlier indices (0-based, sorted ascending) and the corresponding modified Z-scores.
