# Output Schema

The output file is `/app/output/stats_report.json`, formatted with 2-space indentation and a trailing newline.

## Top-Level Structure

The report contains three top-level keys: `config`, `experiments`, and `summary`.

## config

A copy of the pipeline configuration from the input config file.

## experiments

An array of experiment results sorted by `experiment_id` lexicographically. Each experiment contains:

- `experiment_id`: string
- `groups`: an object keyed by group name (sorted alphabetically), each containing:
  - `n`: integer sample size
  - `mean`: float
  - `trimmed_mean`: float (using fractional trimming)
  - `median`: float
  - `variance`: float or null
  - `sd`: float or null
  - `mad`: float (unscaled MAD, the raw median of absolute deviations)
  - `mad_scaled`: float (MAD * 1.4826)
  - `skewness`: float or null
  - `min`: float
  - `max`: float
  - `outlier_indices`: array of integers (0-based indices in the original order, sorted ascending)
  - `outlier_modified_z`: array of floats (modified Z-scores corresponding to outlier_indices)
- `comparisons`: array of pairwise comparison objects sorted by (group_a, group_b), each containing:
  - `group_a`: string
  - `group_b`: string
  - `t_statistic`: float or null
  - `welch_df`: float or null (not rounded to integer)
  - `p_value`: float or null
  - `significant`: boolean or null
  - `hedges_g`: float or null
  - `ci_lower`: float or null (bootstrap CI lower bound)
  - `ci_upper`: float or null (bootstrap CI upper bound)
- `correlation_matrix`: object containing:
  - `group_names`: array of group names sorted alphabetically
  - `matrix`: 2D array of floats or nulls

## summary

- `total_experiments`: integer
- `total_groups`: integer (sum across all experiments)
- `total_comparisons`: integer
- `total_outliers_detected`: integer
- `significant_comparisons`: integer (count of comparisons where significant is true)

## Rounding

All floating-point values are rounded to the number of decimal places specified by `rounding_decimals` in the configuration.
