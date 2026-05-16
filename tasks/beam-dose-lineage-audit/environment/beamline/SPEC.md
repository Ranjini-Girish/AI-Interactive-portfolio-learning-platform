# Beam dose lineage audit

All inputs live under `/app/beamline/`. The tree is read-only. All outputs under `/app/audit/` must be UTF-8 JSON with two-space indentation, lexicographically sorted object keys at every depth, and exactly one trailing newline.

## Inputs

`pool_state.json` contains integer `as_of_minute` and positive integer `recent_shot_k`.

`policy/tier_rules.json` maps tier names to objects with non-negative integers `max_dose_mgy`, `min_quality_pct`, `window_grace_min`, and `capacity_weight`.

Each `profiles/*.json` file has string `profile_id`, integer `dark_pulse`, integer `saturation_pulse`, and integer `gain_umgy_per_pulse`. A pulse row is usable only when `pulse - dark_pulse > 0` and `pulse < saturation_pulse`.

Each `specimens/*.json` file has string `specimen_id`, string `tier`, integer `planned_dose_mgy`, and array `parent_ids`. Parent ids form lineage edges from parent to child. Unknown parent ids are ignored. A specimen in any lineage cycle has lineage status `cyclic`.

Each `windows/*.json` file has string `window_id`, string `station_id`, integers `start_minute`, `end_minute`, and `capacity_weight_limit`. A run can use a window when station ids match and `scheduled_minute` is between `start_minute - tier.window_grace_min` and `end_minute + tier.window_grace_min`, inclusive. If several windows match, choose the one with smallest `end_minute`, then smallest `window_id`.

Each `runs/*.json` file has string `run_id`, string `specimen_id`, string `profile_id`, string `station_id`, integer `scheduled_minute`, integer `quality_pct`, and array `pulses` in chronological order.

`incidents/events.json` contains array `events` in file order. An event is usable only when `accepted` is not false, `minute <= as_of_minute`, and its kind is one of `calibration_shift`, `lineage_contam`, `specimen_hold`, `window_freeze`, or `dose_override`. Otherwise it increments `ignored_incident_events` and has no effect. Required fields are `profile_id` and integer `delta_umgy_per_pulse` for `calibration_shift`, `specimen_id` for `lineage_contam` and `specimen_hold`, `window_id` for `window_freeze`, and `run_id` plus integer `dose_mgy` for `dose_override`. Events with required ids missing from the relevant catalogue are ignored.

## Derived rules

For each profile, accepted calibration shifts apply in file order and sum into the profile gain. Effective gain may be negative; keep integer arithmetic.

For each run, keep usable pulses, take the last `recent_shot_k`, sort those adjusted pulses ascending, and take the median; for an even count use floor average of the two middle values. If no pulse survives, median adjusted pulse and effective dose are `null`. Otherwise `effective_dose_mgy = (median_adjusted_pulse * effective_gain_umgy_per_pulse) // 1000`. A matching accepted `dose_override` replaces the effective dose; latest minute wins, then later file order.

Accepted lineage contamination starts at the named specimen and propagates through child edges to all descendants. Emit `direct_contam` for seeds, `inherited_contam` for descendants, and the minimum edge depth from any seed. Cycle status outranks contamination status.

Run status precedence is: `cyclic_lineage`, `lineage_contaminated`, `specimen_hold`, `window_frozen`, `no_window`, `bad_quality`, `over_dose`, `missing_shots`, `ok`. Quality and dose checks use the run specimen's tier rule. A frozen window is one named by any accepted `window_freeze`.

Reason tags are sorted unique strings. Include the final status, `calibration_shift:<profile_id>` when a run's profile has any accepted shift, `dose_override:<run_id>` when an override is used, `contam_depth:<N>` for contaminated non-cyclic specimens, `hold:<specimen_id>` for active holds, and `window_freeze:<window_id>` for frozen matched windows.

Window utilization counts every run assigned to that window in `assigned_runs`. Only statuses `ok`, `bad_quality`, and `over_dose` charge capacity. Frozen windows charge zero and have status `frozen`; otherwise status is `over_capacity` when charged weight is greater than `capacity_weight_limit`, else `within_capacity`.

## Outputs

Environment overrides: `BDL_DATA_DIR` defaults to `/app/beamline`; `BDL_AUDIT_DIR` defaults to `/app/audit`.

`dose_assessment.json` has key `runs`, an array sorted by `run_id`. Each row has `run_id`, `specimen_id`, `profile_id`, `window_id` (string or null), `median_adjusted_pulse` (integer or null), `effective_dose_mgy` (integer or null), `status`, and `reasons`.

`lineage_impact.json` has key `specimens`, an array sorted by `specimen_id`. Each row has `specimen_id`, `tier`, `parents` sorted ascending, `lineage_status`, and `contam_depth` (integer or null).

`window_utilization.json` has key `windows`, an array sorted by `window_id`. Each row has `window_id`, `station_id`, `assigned_runs` sorted ascending, `charged_weight`, `capacity_limit`, and `status`.

`summary.json` has exactly `as_of_minute`, `run_count`, `specimen_count`, `ignored_incident_events`, `frozen_windows`, `status_counts`, and `lineage_status_counts`.

Canonical hash checks serialize fragments with sorted object keys, compact separators, no ASCII escaping, and one trailing newline.
