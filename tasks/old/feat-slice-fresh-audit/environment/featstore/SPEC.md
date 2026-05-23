# Feature slice freshness audit

Inputs live beside this file. The audit reads `policy.json`, `pool_state.json`, `incidents.json`, and every `*.json` file directly under `slices/`. Paths under `clusters/`, `registry/`, and `anchors/` are packaging noise only.

## Canonical JSON

Emit every artifact as JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Policy

- `row_floors` maps `gold`, `silver`, and `bronze` to minimum integer row counts.
- `staleness_days` maps the same tier names to inclusive day budgets.
- `lineage_grace_days` (integer): allowed gap between a child slice refresh day and its parent's refresh day.

Tier rank high to low is `gold`, `silver`, `bronze`, then `underfilled`.

## Pool state

- `current_day` (integer): evaluation day for staleness and compromise timing.

## Capacity tier

For a slice with `row_count`, the capacity tier is the highest rank whose floor is met; if none are met the capacity tier is `underfilled`.

## Base and effective tier

`base_tier` is the lower rank between `declared_tier` and the capacity tier. Incident notes with `kind` `force_tier` replace `base_tier` with `forced_tier` when `slice_id` matches. Sort `force_tier` notes by ascending `slice_id` before applying.

## Cluster compromise

Notes with `kind` `cluster_compromise` apply when `effective_day <= current_day`. Every slice whose `cluster` equals the note's `cluster` is quarantined: `effective_row_count` is `0` and freshness becomes `quarantined` regardless of other rules.

## Staleness and lineage

For non-quarantined slices, compute parent freshness first (parents always appear earlier in ascending `slice_id` order in the bundled dataset). A slice is `stale` when `current_day - last_refresh_day` exceeds `staleness_days[effective_tier]`, using the `bronze` budget when `effective_tier` is `underfilled`.

A non-quarantined slice with a `lineage_parent` has `lineage_lag` when the parent freshness is not `fresh`, or when `last_refresh_day < parent.last_refresh_day - lineage_grace_days`.

## Freshness precedence

Emit exactly one freshness label per slice with priority `quarantined`, then `stale`, then `lineage_lag`, then `fresh`.

## Outputs

Write five files to the audit directory:

1. `slice_profiles.json` with keys `current_day` then `slices`. Each slice object includes `cluster`, `effective_row_count`, `effective_tier`, `freshness`, `last_refresh_day`, `lineage_parent` (JSON null when absent), `row_count`, and `slice_id`. Sort `slices` by `slice_id` ascending.
2. `cluster_rollups.json` with keys `clusters` then `current_day`. `clusters` maps cluster name to counts for `fresh`, `lineage_lag`, `quarantined`, and `stale`. Cluster names sorted lexicographically; inner count keys sorted lexicographically.
3. `lineage_events.json` with `events`, sorted by `slice_id` ascending. Include one event per slice whose final freshness is `lineage_lag`, carrying `lag_days` (`last_refresh_day - parent.last_refresh_day`), `parent_freshness`, `parent_slice_id`, and `slice_id`.
4. `capacity_summary.json` with keys `tiers` then `underfilled_slices`. `tiers` counts slices by `effective_tier` among non-quarantined rows. `underfilled_slices` lists slice ids whose capacity tier is `underfilled`, sorted ascending.
5. `summary.json` with keys `clusters`, `current_day`, `quarantined_total`, `slices_total`, and `stale_total`.

## Tooling

Read `FSF_DATA_DIR` defaulting to `/app/featstore` and `FSF_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
