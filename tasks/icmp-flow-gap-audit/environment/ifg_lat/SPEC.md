# Normative specification — `ifg_lat` bundle

All paths below are relative to `/app/ifg_lat/` unless noted. Read JSON in UTF-8. Lists that represent deterministic bundles must be sorted as stated before serialization.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `incident_log.json`, every `items/*.json` file in ascending ASCII filename order, `anchors/a.json`, `anchors/b.json`, and `ancillary/x.json`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing mirrors the harness: when `PREFIX_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/ifg_lat/`; when `PREFIX_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. Replace `PREFIX` with the three-letter code from the task instruction.

## Incident common shape

`incident_log.json` contains an `events` array. Only events with `"accepted": true` apply. Unless a task section says otherwise, ignore unknown fields without error.


## Flow sequence gap audit

Items have string `flow_id` and integer `seq`. Sum accepted `flow_skew` incident `delta` integers per `flow_id` and add to every matching item `seq` before grouping.

For each flow sort adjusted sequences ascending. `min_gap` is the minimum positive gap between consecutive sorted values when at least two samples exist, otherwise null.

Emit `flow_gaps.json` with `flows` sorted by `flow_id`, each containing `flow_id`, sorted integer list `sorted_seq`, and nullable integer `min_gap`. Emit `summary.json` with integer `flows` and `current_day`.
