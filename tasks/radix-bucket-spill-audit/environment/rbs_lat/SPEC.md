# Normative specification — `rbs_lat` bundle

All paths below are relative to `/app/rbs_lat/` unless noted. Read JSON in UTF-8. Lists that represent deterministic bundles must be sorted as stated before serialization.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `incident_log.json`, every `items/*.json` file in ascending ASCII filename order, `anchors/a.json`, `anchors/b.json`, and `ancillary/x.json`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing mirrors the harness: when `PREFIX_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/rbs_lat/`; when `PREFIX_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. Replace `PREFIX` with the three-letter code from the task instruction.

## Incident common shape

`incident_log.json` contains an `events` array. Only events with `"accepted": true` apply. Unless a task section says otherwise, ignore unknown fields without error.


## Radix bucket spill audit

`policy.num_buckets` is a positive integer `n`. `policy.per_bucket_cap` is integer capacity `cap`. Each item has `record_id`, integer `key`, integer `mass`.

Bucket index is `key % n`. For each accepted `mass_nudge_bucket` incident add integer `delta` to every item mass whose bucket equals the incident `bucket` before aggregation.

Sum `mass_effective` per bucket. `spill` for a bucket is `max(0, total_mass - cap)`. `spill_total` sums spill across buckets.

Emit `bucket_fill.json` with `rows` sorted by `(bucket, record_id)` ascending, each with `record_id`, `key`, `bucket`, `mass_effective`; `buckets` array length `n` in ascending bucket id with `total_mass` and `spill`; and `spill_total`. Emit `summary.json` with `buckets`, `cap`, `current_day`.
