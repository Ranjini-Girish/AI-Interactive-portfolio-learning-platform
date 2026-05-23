# Normative specification — `tmb_lat` bundle

All paths below are relative to `/app/tmb_lat/` unless noted. Read JSON in UTF-8. Lists that represent deterministic bundles must be sorted as stated before serialization.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `incident_log.json`, every `items/*.json` file in ascending ASCII filename order, `anchors/a.json`, `anchors/b.json`, and `ancillary/x.json`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing mirrors the harness: when `PREFIX_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/tmb_lat/`; when `PREFIX_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. Replace `PREFIX` with the three-letter code from the task instruction.

## Incident common shape

`incident_log.json` contains an `events` array. Only events with `"accepted": true` apply. Unless a task section says otherwise, ignore unknown fields without error.


## Tier mask blind audit

`policy.tier_bits` maps tier names to disjoint power-of-two integer bit channels. Each item has `scope_id`, `tier`, and integer `base_mask`.

Let `disabled_bits` be the bitwise OR of `tier_bits[t]` for every accepted incident with `kind` equal to `disable_tier` and matching `tier` string.

For each item compute `effective_mask = (base_mask OR tier_bits[item tier]) AND (NOT disabled_bits)` using unsigned 32-bit semantics for the bitwise operations described. Integer `popcount` is the population count of `effective_mask`.

Emit `mask_rows.json` with `scopes` sorted by `scope_id` ascending, each object carrying `scope_id`, `tier`, `effective_mask`, and `popcount`. Emit `summary.json` with `current_day`, integer `scopes`, integer `popcount_sum`, and integer `disabled_bits`.
