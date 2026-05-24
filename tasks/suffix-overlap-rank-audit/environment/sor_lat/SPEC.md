# Normative specification — `sor_lat` bundle

All paths below are relative to `/app/sor_lat/` unless noted. Read JSON in UTF-8. Lists that represent deterministic bundles must be sorted as stated before serialization.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `incident_log.json`, every `items/*.json` file in ascending ASCII filename order, `anchors/a.json`, `anchors/b.json`, and `ancillary/x.json`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing mirrors the harness: when `PREFIX_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/sor_lat/`; when `PREFIX_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. Replace `PREFIX` with the three-letter code from the task instruction.

## Incident common shape

`incident_log.json` contains an `events` array. Only events with `"accepted": true` apply. Unless a task section says otherwise, ignore unknown fields without error.


## Suffix overlap audit

Items contain `id` and `text`. Score each string by its character length. `best_id` is the id with maximal score; tie-break ASCII larger id wins.

For every unordered pair of distinct items where one string ends with the first character of the other and the other string length exceeds 1, record `overlap_len` fixed to 1 with `pair` sorted lexicographically. Sort `edge_overlaps` by `pair`.

Emit `suffix_rank.json` with `best_id`, `best_score`, `edge_overlaps`. Emit `summary.json` with `strings` count and `current_day`.
