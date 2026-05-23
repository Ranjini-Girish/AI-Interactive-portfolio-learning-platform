# Finding Types

Each finding has `finding_type`, `severity` (from `policy.finding_severity`),
`severity_rank` (from `policy.severity_ranks`), `event_id`, `station_id`, `pick_id`,
and `evidence`. Fields that don't apply are `null`.

## `insufficient_picks`
- Emitted when a processable event has fewer than `min_usable_picks` eligible picks.
- Evidence: `eligible_picks`, `min_required`, `raw_pick_count`.

## `high_residual_rms`
- Emitted when a localized event's `rms_residual_s` exceeds `policy.high_rms_threshold_s`.
- Evidence: `rms_residual_s`, `threshold_s`.

## `large_azimuth_gap`
- Emitted when a localized event's `azimuth_gap_deg` exceeds `policy.max_azimuth_gap_deg`.
- Evidence: `azimuth_gap_deg`, `threshold_deg`.

## `depth_at_boundary`
- Emitted when the final depth equals exactly `min_depth_km` or `max_depth_km`.
- Evidence: `depth_km`, `min_depth_km`, `max_depth_km`.

## `shallow_depth`
- Emitted when the final depth is strictly less than `policy.shallow_depth_km`.
- Evidence: `depth_km`, `threshold_km`.

## `station_distance_warning`
- Emitted when `nearest_station_km > policy.near_station_threshold_km`.
- Evidence: `nearest_station_km`, `threshold_km`.

## `magnitude_outlier`
- Emitted per-pick when a single-station magnitude deviates from the event mean by more
  than `policy.magnitude_outlier_z * ml_uncertainty`.
- `evidence.deviation` is **signed**: `deviation = mag_i - ml` (positive when the
  single-station estimate is above the event mean, negative when below).
- If `ml_uncertainty` is zero, no outlier finding is emitted.
- Evidence: `station_magnitude`, `event_magnitude`, `deviation`, `threshold`.

## `rejected_pick`
- Emitted for every pick that is NOT used in the final solution.
- Evidence `reason` is determined by the **first** failing check in this exact order:

  1. `unknown_station`   — `station_id` not found in `network/stations.csv`.
  2. `station_disabled`  — station exists but `enabled` field is not exactly `"true"`.
  3. `excluded_station`  — station exists and is enabled, but `station_id` appears in
                           `exclusions.json → excluded_stations`.
  4. `unknown_phase`     — `phase` value has no matching velocity layer for any depth.
  5. `nonpositive_weight`— `weight` is zero or negative.
  6. `pick_status`       — `status` is not exactly `"use"`.
  7. `residual`          — pick passed all eligibility checks but `|residual|` exceeded
                           `policy.residual_reject_s` during the outlier-rejection pass.

- For `residual` rejections, evidence also includes `residual_s` and `threshold_s`.
- All other rejection reasons have only the `reason` key in evidence.
