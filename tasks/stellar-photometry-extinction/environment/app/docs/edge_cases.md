# Edge Cases

## Per-observation `mag_uncertainty`

The reported uncertainty is **floored** at `policy.uncertainty_floor_mag`
before any weight, fit, or chi-squared computation. The original CSV value is
not used directly when it is smaller. Floor is applied identically to standard
and program-star rows.

## Filter completeness

`instrument.json → filters` is the canonical filter list. Every `(night_id,
filter)` pair in the cross product appears in `per_night_calibration`, even
filters that were never observed on that night (those will have status
`insufficient_standards` once filtered for standards, with all-zero numeric
fields). Filters not listed in `instrument.json` but present in the data are
silently ignored — they don't appear in `per_night_calibration` or
`per_star_lightcurves`.

## Catalog magnitudes

A standard star may have an empty `V_mag`, `B_mag`, or `R_mag` cell. That
star simply doesn't contribute to fits in the missing band; the row in
`observations` for that band still counts toward `n_total_observations` for
that `(night, filter)` pair but never toward `n_standards_used`.

## Color-term correction and missing color index

When `instrument.color_terms[filter]` is non-zero, the fit uses
`Δm = instrumental_mag − catalog_mag − ct · (B_mag − V_mag)`.
If a standard star lacks `B_mag` **or** `V_mag`, the color index cannot be
computed and that star is silently dropped from the candidate pool for
**every** filter whose color term is non-zero — even if the star has a valid
catalog magnitude in the target filter. For a filter whose color term is
exactly `0.0`, the color index is irrelevant and the star is still eligible
as long as the target-filter magnitude exists.

## Exclusions ordering

`excluded_nights` short-circuits everything for that night. `excluded_filters_per_night`
applies only to filters listed there for that night. `excluded_stars` removes
the star both as a standard candidate and as a program lightcurve target.
`excluded_observations` drops only the named `image_id` rows; the rest of the
night/filter remains active.

A row that is in `excluded_observations` is still counted in
`n_total_observations` for its `(night, filter)` but is removed from the
candidate list before any fit, calibrated-magnitude derivation, or lightcurve
contribution.

## Overlapping exclusions

A filter may appear in `excluded_filters_per_night` on a night that is also in
`excluded_nights`. In this case the calibration status must be `excluded_night`
(night-level exclusion takes precedence), but the `excluded_filter` **finding**
must still be emitted — every entry in `excluded_filters_per_night` produces
exactly one `excluded_filter` finding regardless of whether the night itself is
excluded. Similarly, an `excluded_observation` whose `star_id` is also in
`excluded_stars` must produce both an `excluded_observation` finding and an
`excluded_star` finding.

## Standard star observations of program stars

A row whose `star_id` is in `catalog/programs.csv` but **not** in
`catalog/standards.csv` cannot constrain the extinction fit, but its
calibrated magnitude is computed normally and contributes to that program
star's lightcurve when the `(night, filter)` is `calibrated`. A `star_id`
that appears in **both** catalogs is treated as a standard for fitting and
also receives a lightcurve entry in the program section.

## MAD = 0

When the median absolute deviation of residuals is exactly zero, the rejection
pass is **skipped entirely** (no rows flagged, no re-fit). This commonly
happens when the candidate list is small enough that the residual median is
exactly equal to all entries.

## Insufficient remaining after rejection

If a rejection pass would leave fewer than `min_standards_per_fit` rows, that
pass is rolled back: the fit from the **previous** pass (or the original fit
for the first pass) is kept, and iteration stops. If the very first pass is
rolled back, `n_outliers_flagged = 0`.

## Multi-pass rejection convergence

The iterative rejection loop runs up to `policy.max_rejection_passes` passes.
It stops early if: (a) `σ_MAD = 0`, (b) no new outliers are flagged, or
(c) removing newly-flagged rows would leave too few standards. Outlier
counts accumulate across accepted passes.

## High-airmass cutoff

Observations with `airmass > policy.max_airmass` are dropped from the
candidate pool before any fit. They still count toward
`n_total_observations` but never contribute to `n_standards_used`,
`n_program_observations`, or lightcurves.

## Degenerate airmass

If every candidate observation lies at exactly the same airmass, the slope is
indeterminate; status becomes `degenerate_airmass_range`. No outlier pass and
no lightcurve impact (the calibrated-magnitude derivation in that filter for
that night is skipped, exactly as it is for any non-`calibrated` status).

## Lightcurve weighting and `chi_squared_reduced`

The weighted mean uses `w = 1 / σ_cal²`, where `σ_cal` is the **combined**
calibrated-magnitude uncertainty (per-observation σ floored, plus zero-point
and slope-propagation terms). The chi-squared sum uses the same
per-observation `σ_cal`, not just the per-row instrumental uncertainty.

## Counting `n_total_observations`

`n_total_observations` for a `(night, filter)` pair is the count of rows in
that night's observations file whose `filter` matches — including standard,
program, excluded-star, and excluded-observation rows. It does **not** depend
on which catalog a star belongs to or which exclusions are active. This count
is reported on **every** row of `per_night_calibration`, including rows whose
status is `excluded_night` or `excluded_filter`; only the slope/intercept,
their uncertainties, residual stddev, outlier and standards-used counts are
zeroed for excluded pairs.

## Sort and rounding

All numeric output fields are rounded to **six** decimal places with
banker's rounding (Python's `round`). Sorting is described in
`output_format.md`. Boolean `is_variable` is preserved as `true`/`false`.
