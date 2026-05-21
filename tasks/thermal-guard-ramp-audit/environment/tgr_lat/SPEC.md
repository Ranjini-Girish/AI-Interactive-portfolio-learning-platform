# Normative specification — `tgr_lat` bundle

All paths are relative to `/app/tgr_lat/` unless noted. Read JSON as UTF-8.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `domain_layout.json`, `incident_log.json`, every `items/item_*.json` in ascending ASCII filename order, both files under `anchors/`, and both files under `ancillary/`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing: when `TGR_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/tgr_lat/`. When `TGR_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`.

## Incident common shape

`incident_log.json` has an `events` array. Only objects with `"accepted": true` apply. Ignore unknown fields.

## Thermal guard ramp

`policy.json` fields: float `ramp_per_day`, float `ceiling`.

`pool_state.json` provides integer `current_day`.

Sum float `value` from every accepted incident with `"kind": "delta_k"` into `global_add` (missing `value` counts as zero).

Each item contains string `zone`, float `base_temp`, and float `guard`.

For each item, compute `raw = base_temp + guard + ramp_per_day * current_day + global_add`. The guarded value is `raw` when `raw < ceiling`, otherwise `ceiling`. Round the guarded value to three decimal places using IEEE-754 ties-to-even for `effective_temp`.

Emit `thermal_ledger.json` as `{"entries": [...]}` sorted ascending by `zone`. Each entry has keys `effective_temp` and `zone`.

Emit `summary.json` with integer `zones` (entry count), integer `day` (same as `current_day`), float `global_add` rounded to three decimals, and float `ceiling` copied from policy without extra rounding beyond normal JSON float rendering.
