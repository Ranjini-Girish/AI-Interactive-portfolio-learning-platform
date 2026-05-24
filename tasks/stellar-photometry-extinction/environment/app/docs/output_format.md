# Output Format

Write exactly one UTF-8 JSON object to the `--out` path with:

- **Two-space indentation** (`indent=2`).
- **Keys sorted alphabetically** at every nesting level (`sort_keys=True`).
- A **single trailing newline** after the closing `}`.
- No carriage returns (`\r`).

This matches Python's `json.dumps(obj, indent=2, sort_keys=True) + "\n"`.
Numeric output fields are rounded to **six** decimal places; integers remain
integers and absent values are JSON `null`.

Top-level keys: `findings`, `per_night_calibration`, `per_star_lightcurves`,
`schema_version`, `summary`. `schema_version` is the integer `1`.

## per_night_calibration

Sorted by `(night_id, filter)`. Each entry has the keys
`airmass_max`, `airmass_min`, `extinction_k`, `extinction_k_uncertainty`,
`filter`, `n_outliers_flagged`, `n_program_observations`,
`n_standards_used`, `n_total_observations`, `night_id`, `residual_stddev`,
`status`, `zero_point`, `zero_point_uncertainty`.

`status` is one of `calibrated`, `insufficient_standards`, `excluded_night`,
`excluded_filter`, `degenerate_airmass_range`. For non-`calibrated` rows, the
numeric fields are zero (or `null` for `airmass_min`/`airmass_max` when no
candidate rows exist for that pair). `n_program_observations` is always zero
on non-`calibrated` rows.

## per_star_lightcurves

Sorted by `(star_id, filter)`. Each entry has the keys
`amplitude_mag`, `chi_squared_reduced`, `filter`, `is_variable`,
`max_calibrated_mag`, `mean_calibrated_mag`, `min_calibrated_mag`, `n_nights`,
`n_observations`, `star_id`, `status`, `stddev_calibrated_mag`.

`status` is one of `calibrated`, `insufficient_observations`, `no_data`. The
boolean `is_variable` is always present; it is `false` on
`insufficient_observations` and `no_data` lightcurves. Numeric fields that
cannot be computed are `null`.

## findings

Sorted by `severity_rank` descending, then `finding_type`, `night_id`,
`filter`, `star_id`, `image_id` ascending. Treat `null` identifiers as the
empty string when comparing.

Each entry has the keys `evidence`, `filter`, `finding_type`, `image_id`,
`night_id`, `severity`, `severity_rank`, `star_id`.

## summary

Has these keys:

- `by_finding_type`: only finding types that occurred (zero-count types are
  omitted).
- `by_severity`: always all five severity keys (`critical`, `high`, `medium`,
  `low`, `info`), even when zero.
- `calibrated_pairs`: number of `(night, filter)` records with status
  `calibrated`.
- `excluded_nights`: number of distinct `night_id`s in
  `exclusions.excluded_nights`.
- `findings_count`: number of findings.
- `flagged_outliers`: total `n_outliers_flagged` across calibrated pairs.
- `insufficient_pairs`: number of `(night, filter)` records with status
  `insufficient_standards`.
- `lightcurves_count`: number of lightcurve entries (program stars × filters
  for non-excluded stars).
- `total_nights`: total entries in `manifest.nights`.
- `total_observations`: sum of all observation rows across every night,
  including excluded.
- `used_program_observations`: total `n_program_observations` across
  calibrated pairs.
- `used_standard_observations`: total `n_standards_used` across calibrated
  pairs.
- `variable_stars`: number of lightcurves with `is_variable = true`.
