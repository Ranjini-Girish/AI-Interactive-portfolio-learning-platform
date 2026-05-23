# Normative specification — `wrm_lat` bundle

All paths below are relative to `/app/wrm_lat/` unless noted. Read JSON in UTF-8. Lists that represent deterministic bundles must be sorted as stated before serialization.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `incident_log.json`, every `items/*.json` file in ascending ASCII filename order, `anchors/a.json`, `anchors/b.json`, and `ancillary/x.json`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing mirrors the harness: when `PREFIX_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/wrm_lat/`; when `PREFIX_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. Replace `PREFIX` with the three-letter code from the task instruction.

## Incident common shape

`incident_log.json` contains an `events` array. Only events with `"accepted": true` apply. Unless a task section says otherwise, ignore unknown fields without error.


## Watchdog reset merge audit

`policy.merge_gap_days` is integer `gap`. Each item has `row_id`, integer `day`, boolean `is_reset`.

Sort items by `(day, row_id)` ascending. Scan in order. Non-reset rows break any active merge run. Reset rows group into segments where consecutive reset rows have day gaps of at most `gap` days between them.

Emit `merged_resets.json` with `segments` array in encounter order, each object containing `start_day`, `end_day`, integer `count`, and sorted `row_ids`. Emit `summary.json` with integer `segments` and `current_day`.
