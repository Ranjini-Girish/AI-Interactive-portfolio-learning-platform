# Normative specification — `zen_lat` bundle

All paths below are relative to `/app/zen_lat/` unless noted. Read JSON in UTF-8. Lists that represent deterministic bundles must be sorted as stated before serialization.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `incident_log.json`, every `items/*.json` file in ascending ASCII filename order, `anchors/a.json`, `anchors/b.json`, and `ancillary/x.json`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing mirrors the harness: when `PREFIX_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/zen_lat/`; when `PREFIX_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. Replace `PREFIX` with the three-letter code from the task instruction.

## Incident common shape

`incident_log.json` contains an `events` array. Only events with `"accepted": true` apply. Unless a task section says otherwise, ignore unknown fields without error.


## Feature score audit

`policy.weights` maps feature names to integer weights. Items have `piece_id` and object `features` mapping strings to integers.

Build banned feature set from accepted `ban_feature` incidents. Score each piece as the sum of `weights[name] * features[name]` for every name in `weights` that is not banned; missing feature keys count as zero.

Emit `piece_scores.json` with `pieces` sorted by descending `score` then ascending `piece_id`, each with `piece_id` and integer `score`. Emit `summary.json` with integer `pieces` and `current_day`.
