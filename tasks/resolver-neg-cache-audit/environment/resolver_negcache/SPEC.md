# Resolver negative cache audit

Inputs live beside this file. Read `policy.json`, `pool_state.json`, `incident_log.json`, every `*.json` under `zones/`, every `*.json` under `queries/`, every `*.json` under `ancillary/`, and every non-empty line in `hints/*.txt`. Ignore `ledger/` paths.

## Canonical JSON

Emit every artifact as JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Policy

- `nxdomain_code` and `nodata_code` (integers): classify negative-cache candidates.
- `nx_ttl_days` and `nodata_ttl_days` (positive integers): base TTL in days before stale grace begins.
- `stale_grace_days` (non-negative integer): extra days after base TTL where status is `stale_grace` instead of `expired`.

## Pool state

- `current_day` (integer): timeline anchor for age and incident eligibility.

## Zone suffix rebinding

Each zone file provides `zone_id` and `suffixes` (array of strings). For every query, ignore the file's `zone_id` field for classification and instead choose the zone whose suffix matches the end of `qname` with the longest suffix length. When two zones tie on length, pick the lexicographically smallest `zone_id`. When no suffix matches, keep the file's original `zone_id`.

## Ancillary TTL bumps

Walk `ancillary/*.json` in ascending ASCII basename order. Each file may include `zone_ttl_bump` mapping zone id to non-negative integer days added to the base TTL for that zone. Later files overwrite earlier values for the same zone key.

## Base TTL classification

Let `age_days = current_day - observed_day` (integer subtraction).

When `response_code` equals neither `nxdomain_code` nor `nodata_code`, the query's `cache_status` is `non_negative` and it is excluded from negative rollups and stale events.

Otherwise compute `effective_ttl` as `nx_ttl_days` or `nodata_ttl_days` plus the ancillary bump for the rebound zone id (zero when absent). Apply TTL rules before hints and incidents:

- `age_days <= effective_ttl` → `fresh`
- `effective_ttl < age_days <= effective_ttl + stale_grace_days` → `stale_grace`
- `age_days > effective_ttl + stale_grace_days` → `expired`

## Hint overrides

Parse each non-empty `hints/*.txt` line as two whitespace-separated tokens: `query_id` then `cache_status`. Collect every line from every hints file, sort by ascending `query_id`, and when the same id appears more than once the later line wins. Apply a hint only when the query id exists and the hinted status is one of `fresh`, `stale_grace`, or `expired`. Hints run after TTL math and before incidents.

## Incident precedence

Consider only events with `day <= current_day`. Sort eligible events by ascending `day`, then ascending `kind`, then ascending primary target (`resolver_id`, `zone_id`, or `query_id` field present). Apply in that order; later rules may override earlier ones only where this section grants higher priority.

| kind | effect |
|------|--------|
| `negative_hold` | matching `query_id` with `observed_day >= day` becomes `stale_grace` |
| `zone_flush` | matching rebound `zone_id` with `observed_day >= day` becomes `flushed` |
| `resolver_compromise` | matching `resolver_id` with `observed_day >= day` becomes `poisoned` |

`resolver_compromise` outranks `zone_flush`, which outranks `negative_hold`, which outranks hints and TTL results.

## Outputs

Write five files to the audit directory:

1. `query_profiles.json` with keys `current_day` then `queries`. Each query row includes `cache_status`, `effective_ttl`, `observed_day`, `qname`, `qtype`, `query_id`, `rebound_zone_id`, `resolver_id`, and `response_code`. Sort `queries` by ascending `query_id`.
2. `zone_rollups.json` with keys `current_day` then `zones`. Each zone object has `zone_id` and `status_counts` mapping every negative-cache status (`expired`, `flushed`, `fresh`, `poisoned`, `stale_grace`) to integer counts for queries with rebound zone equal to that id and a status other than `non_negative`. Omit `non_negative` from `status_counts`. Sort `zones` by ascending `zone_id`; sort keys inside each `status_counts` lexicographically.
3. `stale_events.json` with keys `current_day` then `events`. Include one event per query whose final `cache_status` is `stale_grace` or `expired`, sorted by `query_id`. Each event carries `age_days`, `cache_status`, `effective_ttl`, `query_id`, `rebound_zone_id`, and `resolver_id`.
4. `incident_journal.json` with keys `applied_events` then `current_day`. `applied_events` lists every incident event with `day <= current_day` in the sort order defined above (objects copied verbatim from the log).
5. `summary.json` with keys `current_day`, `expired_total`, `flushed_total`, `fresh_total`, `negative_total`, `non_negative_total`, `poisoned_total`, `queries_total`, `stale_grace_total`, and `zones`. `zones` is the sorted distinct list of rebound zone ids across all queries. `negative_total` counts queries whose final status is not `non_negative`. Other `*_total` fields count queries with that exact final status.

## Tooling

Read `RNCA_DATA_DIR` defaulting to `/app/resolver_negcache` and `RNCA_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
