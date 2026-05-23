# Normative specification — `tgr_lat` bundle

All paths are relative to `/app/tgr_lat/` unless noted. Read JSON as UTF-8.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `domain_layout.json`, `incident_log.json`, every `items/item_*.json` in ascending ASCII filename order, both files under `anchors/`, and both files under `ancillary/`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing: when `TGR_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/tgr_lat/`. When `TGR_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`.

## Incident common shape

`incident_log.json` has an `events` array. Process objects in ascending array index order. Only objects with `"accepted": true` participate. Ignore unknown fields on any object. If `"accepted"` is missing, treat the event as not accepted. Unknown `"kind"` values are ignored in their entirety even when accepted.

## Accepted incident kinds

Each kind lists required semantics when accepted is true. Missing numeric fields count as zero. Missing string fields make that event a no-op for kinds that require a zone name.

### `delta_k`

Add float `value` to running `global_add`.

### `ramp_shave`

Add float `amount` to running `ramp_shave_total`.

### `zone_bias`

Let `z` be string `zone` and `b` float `bias`. Add `b` to running `zone_bias[z]`. If `zone` is missing or empty, the event is a no-op.

### `guard_suppress`

Let `z` be string `zone`. If `z` is missing or empty, the event is a no-op. Otherwise, if `z` has not yet been recorded as suppressed, record `z` as suppressed and increment `guard_suppress_events` by one. If `z` was already suppressed by an earlier accepted `guard_suppress`, this duplicate is a no-op for suppression state and does not increment `guard_suppress_events`.

## Thermal guard ramp and ledger

`policy.json` fields: float `ramp_per_day`, float `ceiling`.

`pool_state.json` provides integer `current_day`.

After the incident scan finishes, define:

- `ramp_linear = ramp_per_day * current_day` where both operands are promoted to float.
- `ramp_effective_raw = ramp_linear - ramp_shave_total`. If `ramp_effective_raw` is less than zero, use zero instead.

For each item (each file under `items/` in ascending ASCII filename order), read string `zone`, float `base_temp`, and float `guard`.

Let `g = 0.0` when `zone` is in the suppressed set from `guard_suppress`; otherwise `g = guard`.

Let `b` be the accumulated `zone_bias` entry for that `zone`, or `0.0` when none exists.

Compute `raw = base_temp + g + ramp_effective_raw + global_add + b`. The guarded scalar is `raw` when `raw < ceiling`, otherwise `ceiling`. Round the guarded scalar to three decimal places using IEEE-754 ties-to-even for `effective_temp`.

Emit `thermal_ledger.json` as `{"entries": [...]}` sorted ascending by `zone`. Each entry has keys `effective_temp` and `zone`.

Emit `summary.json` as an object whose keys are exactly these eight keys:

- integer `zones`: number of ledger entries (same as the number of item files processed).
- integer `day`: copy `current_day` from `pool_state.json` as an integer.
- float `global_add`: `global_add` rounded to three decimals using the same rounding rule as temperatures.
- float `ceiling`: copied from policy as a float without an extra quantize pass beyond normal JSON float rendering.
- float `ramp_effective`: `ramp_effective_raw` after the zero floor, rounded to three decimals with the same rounding rule.
- float `ramp_shave_total`: `ramp_shave_total` rounded to three decimals with the same rounding rule.
- integer `zone_bias_events`: count of accepted `zone_bias` events (including no-ops that still count as accepted rows with kind `zone_bias`).
- integer `guard_suppress_events`: count defined only by first-time `guard_suppress` acceptances as specified above.
