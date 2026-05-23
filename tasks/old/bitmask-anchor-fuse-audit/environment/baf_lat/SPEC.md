# Normative specification — `baf_lat` bundle

All paths are relative to `/app/baf_lat/` unless noted. Read JSON as UTF-8.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `domain_layout.json`, `incident_log.json`, every `items/item_*.json` in ascending ASCII filename order, both files under `anchors/`, and both files under `ancillary/`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing: when `BAF_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/baf_lat/`. When `BAF_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`.

## Incident common shape

`incident_log.json` has an `events` array. Only objects with `"accepted": true` apply. Ignore unknown fields.

## Fuse ledger

`policy.json` fields: integer `fuse_mask`, integer `base_or`, float `tier_factor`.

Compute `xor_acc` starting at zero. For each accepted event with `"kind": "xor_acc"`, replace `xor_acc` with `xor_acc XOR int(value)` where missing `value` counts as zero.

Each item contains string `id`, integer `mask` in `[0,255]`, and float `scale`.

For every item in ascending ASCII filename order, let `eff = ((mask XOR xor_acc) AND fuse_mask) OR base_or` using 32-bit integer semantics restricted to the low eight bits by the fixture range. Emit `effective_mask` as the integer `eff` and `score` as `popcount(eff) * scale * tier_factor` rounded to four decimals using IEEE-754 ties-to-even.

`popcount` counts set bits on the non-negative integer `eff`.

Emit `fuse_ledger.json` as `{"entries": [...]}` sorted ascending by `id` then `effective_mask`. Each entry has keys `effective_mask`, `id`, `score`.

Emit `summary.json` with integer `entries`, float `total_score` (sum of entry scores, four-decimal rounding), and integer `xor_acc` after processing all incidents.
