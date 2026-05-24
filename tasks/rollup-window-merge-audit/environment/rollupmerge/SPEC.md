# Rollup window merge audit

Inputs live beside this file. Read `policy.json`, `pool_state.json`, `incidents.json`, every `*.json` under `overlays/`, every `*.json` under `series/`, and every non-empty line in `anchors/*.txt`. Paths under `ledger/` are packaging noise only.

## Canonical JSON

Emit every artifact as JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Policy

- `bucket_days` (positive integer): width of each rollup bucket in days.
- `grace_days` (non-negative integer): watermark staleness threshold.
- `value_floor` (integer): ignore samples whose `value` is strictly less than this floor.

## Pool state

- `current_day`, `window_start_day`, `window_end_day` (integers): inclusive audit window on the day axis.

A **complete bucket** starts at `window_start_day + k * bucket_days` for `k = 0, 1, …` while `bucket_start + bucket_days - 1 <= window_end_day`. Partial trailing buckets are ignored everywhere.

For a sample day `d`, its bucket start is `window_start_day + ((d - window_start_day) / bucket_days) * bucket_days` using integer division toward zero. Only samples with `window_start_day <= d <= window_end_day` and `value >= value_floor` participate.

## Overlay merge

Walk `overlays/*.json` in ascending ASCII basename order. Later files overwrite earlier values for the same key:

- `min_sample_count` (integer, default 1)
- `bucket_cap` (integer, default unlimited)
- `exclude_sources` (array of source_id strings): union every listed id

## Incidents and anchors

Parse `incidents.json` `events` entries with `kind`, `source_id`, `day`, and `accepted`. Collect `anchors/*.txt` lines as two whitespace-separated tokens: `series_id` then `forced_status`. Sort the combined anchor list by ascending `series_id`; when the same id appears more than once, the later line wins. Apply anchors only for ids present in the series set.

Accepted `source_compromise` events quarantine every series whose `source_id` matches, regardless of watermark or anchors. `forced_status` value `hold` sets profile status `hold` when not quarantined.

## Per-series profile

For each series file (basename without `.json` must equal `series_id`):

- `stale_flag` is true when `current_day - watermark_day > grace_days`.
- `status` is `quarantined` when its source is compromised, else `hold` when anchor forces hold, else `stale` when `stale_flag`, else `ok`.
- `complete_buckets` lists bucket starts (ascending) where the series has at least `min_sample_count` participating samples inside that bucket's day range, the bucket is complete, and the source is not excluded.
- `window_sum` is the sum of participating sample values inside complete buckets, or JSON `null` when quarantined.

Sort the `series` array by ascending `series_id`.

## Bucket rollups

For each complete bucket, collect contributors with `complete_buckets` containing that start. Sum each contributor's participating values inside that bucket only. Sort contributors by `series_id` ascending, keep the first `bucket_cap` entries, and emit objects with `series_id` and `sum`. Sort the top-level `buckets` array by `bucket_start` ascending.

Excluded sources never appear in bucket rollups but still appear in `series_profiles.json`.

## Stale and compromise reports

`stale_report.json` lists every series with `stale_flag` true and status not `quarantined`, sorted by `series_id`, each row carrying `series_id`, `source_id`, and `watermark_day`.

`compromise_report.json` carries `sources` (distinct compromised source_id values, sorted) and `series` (quarantined rows sorted by `series_id` with `series_id`, `source_id`, `watermark_day`).

## Summary

`summary.json` keys: `bucket_count`, `complete_bucket_starts`, `current_day`, `quarantined_total`, `series_total`, `stale_total`, `window_end_day`, `window_start_day`. `complete_bucket_starts` lists every complete bucket start ascending. `stale_total` counts profiles with `stale_flag` true. `quarantined_total` counts profiles with status `quarantined`.

## Outputs

Write five files to the audit directory:

1. `series_profiles.json` with keys `series` then `window_end_day` and `window_start_day` copied from pool state.
2. `bucket_rollups.json` with keys `buckets`, `window_end_day`, `window_start_day`.
3. `stale_report.json` with key `series`.
4. `compromise_report.json` with keys `series` then `sources`.
5. `summary.json` as above.

## Tooling

Read `RWM_DATA_DIR` defaulting to `/app/rollupmerge` and `RWM_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
