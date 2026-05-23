# Normative specification — `lep_lat` bundle

All paths below are relative to `/app/lep_lat/` unless noted. Read JSON in UTF-8. Lists that represent deterministic bundles must be sorted as stated before serialization.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `incident_log.json`, every `items/*.json` file in ascending ASCII filename order, `anchors/a.json`, `anchors/b.json`, and `ancillary/x.json`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing mirrors the harness: when `PREFIX_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/lep_lat/`; when `PREFIX_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. Replace `PREFIX` with the three-letter code from the task instruction.

## Incident common shape

`incident_log.json` contains an `events` array. Only events with `"accepted": true` apply. Unless a task section says otherwise, ignore unknown fields without error.


## Lockfile edge prune audit

Items have `edge_id`, `pkg`, `version` strings. Remove any item whose `pkg` equals the `pkg` field of an accepted `prune_pkg` incident.

Emit `lock_edges.json` with `edges` sorted by `(pkg, version, edge_id)` ascending. Emit `summary.json` with integer `edges_kept` and `current_day`.
