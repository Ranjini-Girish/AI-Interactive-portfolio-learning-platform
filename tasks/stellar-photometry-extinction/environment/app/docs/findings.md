# Finding Types

Every finding has the keys `finding_type`, `severity`, `severity_rank`
(integer from `policy.severity_ranks`), `night_id`, `filter`, `star_id`,
`image_id`, and `evidence`. Fields that don't apply are `null`.
`severity_rank` for each emitted finding is looked up via the finding's
`severity` (which itself comes from `policy.finding_severity[finding_type]`).

## Calibration findings

### `insufficient_standards`
Emitted on a non-excluded `(night, filter)` pair where the eligible
standard-star observation count is below `min_standards_per_fit`.
Evidence: `n_standards_observed`, `min_required`, `n_total_observations`.
Severity per `policy.finding_severity`.

### `bad_night_residuals`
Emitted on a calibrated pair whose `residual_stddev` exceeds
`bad_night_residual_stddev`. Evidence: `residual_stddev`, `threshold`,
`n_standards_used`.

### `negative_extinction`
Emitted on a calibrated pair whose `extinction_k < negative_extinction_threshold`.
Evidence: `extinction_k`, `threshold`.

### `large_zero_point_uncertainty`
Emitted on a calibrated pair whose `zero_point_uncertainty` exceeds
`large_zero_point_uncertainty`. Evidence: `zero_point_uncertainty`,
`threshold`.

### `degenerate_airmass_range`
Emitted on a non-excluded pair whose candidate observations all lie at the
same airmass (the slope cannot be solved). Evidence:
`n_standards_observed`.

### `outlier_observation`
Emitted **once per flagged outlier** during the MAD rejection pass that was
accepted (not reverted). Carries the `night_id`, `filter`, and `image_id` of
the flagged row. Evidence: `k_mad`.

## Lightcurve findings

### `program_star_no_data`
Emitted when a non-excluded program star has zero contributing observations
in a given filter. Evidence empty. Carries `star_id` and `filter`.

### `insufficient_lightcurve_observations`
Emitted when a non-excluded program star's contributing observations on
calibrated pairs in a filter are fewer than
`min_observations_per_lightcurve`. Evidence: `n_observations`, `min_required`.
Carries `star_id` and `filter`.

### `variable_star_detected`
Emitted when a calibrated lightcurve has `chi_squared_reduced` exceeding
`variability_chi2_threshold`. Evidence: `chi_squared_reduced`, `threshold`,
`amplitude_mag`, `n_observations`. Carries `star_id` and `filter`.

## Bookkeeping findings

These describe explicit exclusions configured in `exclusions.json`. They are
always severity `info` and carry no evidence keys (the `evidence` field is
the empty object `{}`).

### `excluded_night`
One per `night_id` in `excluded_nights`.

### `excluded_filter`
One per `(night_id, filter)` pair in `excluded_filters_per_night`.

### `excluded_star`
One per `star_id` in `excluded_stars`.

### `excluded_observation`
One per `image_id` in `excluded_observations`.
