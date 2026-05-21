# Normative specification — `qdw_lat` bundle

All paths are relative to `/app/qdw_lat/` unless noted. Read JSON as UTF-8. Lists must follow the sorting rules before serialization.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `domain_layout.json`, `incident_log.json`, every `items/item_*.json` in ascending ASCII filename order, both files under `anchors/`, and both files under `ancillary/`. The pool and layout files are integrity witnesses for this bundle revision and do not change the dedupe math unless a future revision says otherwise; they must still parse as JSON objects. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing: when `QDW_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/qdw_lat/`. When `QDW_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`.

## Incident common shape

`incident_log.json` has an `events` array. Only objects with `"accepted": true` apply. Ignore unknown fields.

## Sliding dedupe window

`policy.json` fields: integer `window` (non-negative), float `idle_floor` (ignored by this batch but must be present as a number).

`incident_log.json` may contain accepted events with `"kind": "window_bump"`. Sum integer `delta` from every accepted `window_bump` (missing `delta` counts as zero). Define `window_effective = window + sum(delta)`.

Iterate `items/item_*.json` in ascending ASCII filename order. Each item must contain integer `seq`, string `key`, float `ts`, and float `weight`.

Maintain `last_accept_ts` per `key` for items that are not suppressed. For each item in iteration order, let `last` be `last_accept_ts[key]` if present, else absent. The item is suppressed when `last` is present and `ts - last <= window_effective` using float arithmetic as read from JSON. If suppressed, set `weight_applied` to `0.0` and do not update `last_accept_ts` for that key. If not suppressed, set `weight_applied` to `weight`, add `weight` to `total_weight`, and set `last_accept_ts[key] = ts`.

Round each `weight_applied` to four decimal places using IEEE-754 ties-to-even. Round `total_weight` to four decimal places the same way for `summary.json`.

Emit `dedupe_ledger.json` as `{"entries": [...]}` where each entry has keys `seq`, `key`, `ts`, `suppressed`, `weight_applied` and the list is sorted ascending by `seq` then `key`.

Emit `summary.json` with integer `entries`, integer `suppressed`, float `total_weight` (four-decimal rounding), and float `window_effective` equal to the effective window as a JSON number (no rounding beyond normal JSON float rendering for integers).
