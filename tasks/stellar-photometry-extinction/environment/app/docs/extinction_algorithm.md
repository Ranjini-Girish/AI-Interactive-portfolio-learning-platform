# Per-(Night, Filter) Extinction Algorithm

The pipeline emits one calibration record for every `(night_id, filter)` pair
in the cross product of `manifest.nights` × `instrument.filters`, regardless of
whether the night was observed in that filter at all. Pairs whose night is
in `exclusions.excluded_nights` get `status = "excluded_night"`. Pairs whose
filter appears in `excluded_filters_per_night` for that night get `status =
"excluded_filter"`. For excluded statuses, every numeric output field in the
calibration record is `0.0` (or `null` for `airmass_min`/`airmass_max`)
**except** `n_total_observations`, which is always the filter-only row count
defined below regardless of whether the pair is excluded.

For a non-excluded `(night, filter)` pair, build the candidate list from
observations rows where:

- the row's `filter` matches,
- `star_id` is in `catalog/standards.csv` and has a non-empty catalog magnitude
  in this filter,
- `star_id` is **not** in `exclusions.excluded_stars`,
- `image_id` is **not** in `exclusions.excluded_observations`.

If there are fewer than `policy.min_standards_per_fit` candidate rows, set
`status = "insufficient_standards"`; the numeric fields of that record are all
zero (`null` for the airmass extremes), and `n_total_observations` is the count
of all rows in this `(night, filter)` whose `filter` matches (regardless of
star type or exclusion).

Otherwise compute, for each candidate row,
`Δm = instrumental_mag − catalog_mag − ct · CI` where `ct` is
`instrument.color_terms[filter]` and `CI` is the standard star's
**catalog color index** `(B_mag − V_mag)`. If `ct` is non-zero and either
`B_mag` or `V_mag` is missing for that standard star, the row **cannot
contribute** to this filter's fit and is silently dropped from the candidate
list (it still counts toward `n_total_observations`). When `ct` is zero the
color-index term vanishes and the formula reduces to
`Δm = instrumental_mag − catalog_mag`.

Then set `σ = max(mag_uncertainty, policy.uncertainty_floor_mag)`,
`w = 1 / σ²`. Skip rows whose effective `σ` is non-positive. Also
skip rows whose `airmass` exceeds `policy.max_airmass` (they remain in
`n_total_observations` but are excluded from the candidate pool).

Fit `Δm ≈ slope · airmass + intercept` by **weighted least squares**:

- `S = Σ wᵢ`
- `x̄ = (Σ wᵢ · Xᵢ) / S`, `ȳ = (Σ wᵢ · Δmᵢ) / S`
- `S_xx = Σ wᵢ · (Xᵢ − x̄)²`
- `S_xy = Σ wᵢ · (Xᵢ − x̄) · (Δmᵢ − ȳ)`
- If `S_xx = 0` (all airmasses equal), set `status =
  "degenerate_airmass_range"` and zero the slope/intercept — but don't set
  insufficient_standards.
- Otherwise `slope = S_xy / S_xx`, `intercept = ȳ − slope · x̄`.
- `slope_var = 1 / S_xx`; `intercept_var = 1/S + x̄² / S_xx`.
- `extinction_k_uncertainty = √slope_var`,
  `zero_point_uncertainty = √intercept_var`.

Compute residuals `rᵢ = Δmᵢ − (slope · Xᵢ + intercept)` for the kept set.

**Iterative outlier rejection.** Up to `policy.max_rejection_passes` passes
(default 1), repeat the following cycle:

1. Compute the unweighted MAD of the **current** residuals:
   `MAD = median(|rᵢ − median(rⱼ)|)`, `σ_MAD = 1.4826 · MAD`.
2. If `σ_MAD = 0`, stop (no further rejection in this or subsequent passes).
3. Flag every row in the **current kept set** with
   `|rᵢ| > policy.mad_outlier_k · σ_MAD`.
4. If no new rows are flagged, stop (convergence).
5. If removing the newly-flagged rows would leave fewer than
   `min_standards_per_fit` in the **cumulative** kept set, **roll back
   this pass** — un-flag its rows, keep the fit from the previous pass,
   and stop.
6. Otherwise accept the flagged rows, re-fit on the updated kept set,
   recompute residuals, and continue to the next pass.

`n_outliers_flagged` is the **total** number of rows removed across all
accepted passes. If the very first pass is rolled back, the original fit
is kept and `n_outliers_flagged = 0`.

`residual_stddev` is the **weighted population residual standard deviation**
of the final fit on the kept subset:
`√(Σ wᵢ · rᵢ² / Σ wᵢ)`. Excluded/insufficient/degenerate pairs carry zero.

The recorded values per `(night, filter)`:

- `airmass_min`, `airmass_max`: extremes over the candidate list before any
  outlier rejection. `null` when the pair is excluded or has no rows. (Note:
  for `insufficient_standards`, candidate list is empty by definition only if
  zero rows; report the extremes of whatever rows existed.)
- `extinction_k`: the final slope.
- `zero_point`: the final intercept.
- `extinction_k_uncertainty`, `zero_point_uncertainty`: from the final fit.
- `residual_stddev`: as above.
- `n_outliers_flagged`: rows rejected by the MAD pass that were not reverted.
- `n_standards_used`: for a `calibrated` pair, the rows that contributed to
  the final fit (after any successful outlier removal). For
  `insufficient_standards` or `degenerate_airmass_range`, this is the number
  of eligible candidate rows that were available (the pool size before the
  fit was attempted). For excluded statuses it is zero.
- `n_total_observations`: count of every observations-file row in this
  `(night, filter)` whose filter matches, regardless of star type or
  exclusion. This is identical for every filter on a given night that is not
  excluded, but counts only the matching-filter rows.
- `n_program_observations`: program-star observations on this `(night, filter)`
  that are eligible (non-excluded star, non-excluded image_id, non-zero σ) and
  whose calibration ended up `calibrated`. Always zero on non-calibrated
  pairs.
- `status`: one of `calibrated`, `insufficient_standards`, `excluded_night`,
  `excluded_filter`, `degenerate_airmass_range`.

# Calibrated magnitudes

For every observation row with a `calibrated` `(night, filter)` pair, the
calibrated magnitude is
`m_cal = instrumental_mag − k · X − zp`. The color-term correction is
**not** applied here because program stars lack catalog magnitudes needed to
compute the color index; the fit already absorbed the mean color effect into
the zero point. Combined uncertainty is
`σ_cal = √( σ² + σ_zp² + (X · σ_k)² )` where `σ` is the floored
per-observation uncertainty. Standard-star observations also carry a
calibrated magnitude for the residual diagnostics, but they are not part of
the program-star lightcurve outputs.

# Program-star lightcurves

For each `program` star (catalog/programs.csv) that is **not** in
`excluded_stars`, and each filter in `instrument.filters`, build a lightcurve
using only that star's observations on calibrated `(night, filter)` pairs,
excluding observations whose `image_id` is in `excluded_observations`. The
emitted record has:

- `n_observations`: number of contributing observations.
- `n_nights`: number of distinct night_ids contributing.
- `min_calibrated_mag`, `max_calibrated_mag`, `amplitude_mag` (`max - min`).
- `mean_calibrated_mag`: weighted mean of the `n_observations` calibrated
  magnitudes using `w = 1/σ_cal²`. `null` if `Σ w` is zero.
- `stddev_calibrated_mag`: weighted population stddev about that mean,
  `√( Σ w · (m − μ)² / Σ w )`. `null` if `Σ w` is zero.
- `chi_squared_reduced`: `χ² / dof` where
  `χ² = Σ ((m − μ) / σ_cal)²` and `dof = n_observations − 1`. `null` when
  `n_observations < 2` or the lightcurve is not eligible for variability
  testing.
- `is_variable`: `true` iff `chi_squared_reduced > variability_chi2_threshold`
  **and** the lightcurve has at least `min_observations_per_lightcurve`
  observations. `false` otherwise.
- `status`: one of `calibrated`, `insufficient_observations` (fewer than
  `min_observations_per_lightcurve`), `no_data` (zero observations).

For `no_data`, every numeric field except the counts is `null`. For
`insufficient_observations`, the min/max/amplitude/mean/stddev are still
computed when at least one observation exists; only `chi_squared_reduced` and
`is_variable` are skipped.
