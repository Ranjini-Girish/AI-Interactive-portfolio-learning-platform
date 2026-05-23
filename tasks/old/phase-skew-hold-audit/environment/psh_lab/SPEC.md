# Phase Skew Hold Lab — Normative SPEC

This file is normative for every field, ordering rule, and edge interaction. The lab root is `/app/psh_lab/`. The audit root is `/app/audit/`. Emit exactly one file: `/app/audit/report.json`.

## Input inventory

Read `policy.json`, `pool_state.json`, `domain_layout.json`, `incident_log.json`, `anchors/window.json`, `anchors/day_floor.json`, and every `streaks/*.json` file. Files under `ancillary/` are packaging context only; they MUST NOT influence numbers in the report.

Each streak file has shape `{"site": "<id>", "rows": [ ... ] }`. Each row has integer `day`, float `phase_deg` on `[0,360)`, float `quality` in `[0,1]`, and string `instrument`.

## Incident semantics

`incident_log.json` contains an `events` array. Supported `kind` values:

- `site_compromise` with string `site` and integer `effective_day`. From that day forward (inclusive) every row for the site is `compromised`.
- `instrument_quarantine` with string `instrument` and integer `effective_day`. From that day forward (inclusive) every row using that instrument id is `quarantined`, regardless of site.

## Anchor semantics

`anchors/day_floor.json` lists `floors` entries `{ "site": "...", "min_day": <int> }`. Any row whose `day` is strictly less than `min_day` for its site is `below_floor`.

`anchors/window.json` lists `windows` entries `{ "site": "...", "start_day": <int>, "end_day": <int> }` inclusive. If a row is not already assigned a higher-severity label by the rules below, and its `day` lies inside any window for its site, its row-level state is `cool`.

## Row-level precedence

Evaluate in this strict order; the first match wins for that row:

1. `below_floor` using day floors.
2. `compromised` using site compromise days.
3. `quarantined` using instrument quarantine days.
4. `weak` when `quality` is strictly less than `policy.min_quality`.
5. `hold` when the row is not the first chronologically for its site after sorting rows by `(day asc, instrument asc)` and the gap `current.day - previous.day` is strictly greater than integer `policy.grace_gap_days`.
6. `cool` using cool windows.
7. otherwise `ok`.

## Site-day aggregation

Group rows by `(site, day)` using the `site` field from the streak file. Sort groups by `site` ascending, then `day` ascending. For each group compute:

- `instruments`: sorted distinct instrument ids present that day.
- `aggregate_state`: the worst row-level state inside the group using severity order `ok < cool < hold < weak < below_floor < quarantined < compromised`.
- `merged_phase_deg`: null unless at least one row in the group is eligible for the merge pool. Eligible rows are those whose row-level state is exactly `ok` or `cool` and whose `quality` is greater than or equal to `policy.min_quality`.

## Circular merge with MAD and mask skip

Let `P` be the list of `phase_deg` values taken from eligible rows in a single `(site, day)` group, preserving paired instrument ids.

1. Compute the circular mean in degrees of `P` using unit-vector averaging on the circle (wrap at 360).
2. For each point, compute its shortest angular distance to that mean in degrees.
3. Let `mad` be the median of those distances. Let `thr = policy.mad_multiplier * max(mad, 0.05)`.
4. For each point, if `instrument_mask_policy[instrument]` exists in `policy.json` and the bitwise AND of `pool_state.instrument_masks[instrument]` with that policy mask is non-zero, the point is **mask-skip** and is always kept. Otherwise keep the point only if its distance is less than or equal to `thr`.
5. If every point would be removed, fall back to the pre-filter list `P` unchanged.
6. The merged value is the circular mean of the kept list, rounded to six decimal places using fixed-point formatting (half away from zero is not required; use Go `strconv.FormatFloat(..., 'f', 6, 64)` semantics).

## Output JSON

Write `/app/audit/report.json` as UTF-8 JSON with ASCII-only text, two-space indentation, sorted object keys at every object level, and a single trailing newline after the closing brace. Top-level keys must be exactly `site_days` then `summary` in that sorted order (JSON key order is lexical: `site_days` precedes `summary`).

`site_days` is an array of objects, each with keys ordered as `aggregate_state`, `day`, `instruments`, `merged_phase_deg`, `site`. `instruments` is sorted ascending. Numeric fields use JSON numbers without unnecessary trailing noise.

`summary` must contain, sorted lexicographically:

- `days_span`: `[min_day, max_day]` observed across all streak rows after ingestion.
- `rows_ingested`: total row count across all streak files.
- `site_day_rows`: length of the `site_days` array.
- `sites_considered`: count of distinct sites discovered while reading streak files.
- `state_counts`: map from each `aggregate_state` string that appears at least once to its frequency; omit keys with zero counts. Sorting inside the map follows JSON’s sorted key order.

## Determinism

The computation must be deterministic for the bundled fixtures. Floating-point literals in inputs are small enough that cross-platform drift is not expected; still, follow the rounding rule for `merged_phase_deg` exactly.
