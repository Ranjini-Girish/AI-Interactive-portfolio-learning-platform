# Labkit multi-plate assay audit — normative contract

All JSON emitted under `/app/audit/` must be UTF-8, end with exactly one newline, use two-space indentation, and sort object keys lexicographically at every depth. Arrays must follow the sort orders stated below. Numbers are JSON numbers (no trailing zeros beyond what JSON emits). Use `null` only where this document explicitly allows it.

## Inputs (read-only)

- `/app/labkit/pool_state.json` contains integer `current_day`.
- `/app/labkit/policy.json` contains positive integers `min_blanks`, `drift_abs_threshold`; number `fallback_blank_value`; and string `ignored_incident_kind_marker` (informational only for humans; processors must still apply the rejection rules in the incident section).
- `/app/labkit/assays.json` maps `assays` objects keyed by `assay_id`. Each assay has `normalization_mode` equal to either `to_blank_median` or `to_standard_curve`. For `to_standard_curve`, the assay also has `std_x_by_level` mapping level names to numeric x used for regression.
- `/app/labkit/batches/index.json` lists `batches` as objects with `batch_id`, `lineage_id`, and `assay_id` (one assay monitored per batch row).
- `/app/labkit/lots/registry.json` maps `lots` objects keyed by `lot_id` with string `reagent_code` (metadata only).
- `/app/labkit/incident_log.json` lists `events` in file order; each event has `kind`, optional `accepted` (default true when absent), integer `day`, optional `lot_id`, optional `note`.
- `/app/labkit/plates/*.json` each describe one plate with string `plate_id`, integer `run_day`, and array `wells`. Every well has string `well_id`, string `role` in `sample`, `blank`, or `std`; optional `sample_id`; optional `assay_id` (required when `role` is `sample` or `std`); number `raw_value`; optional `lot_id` (required when `role` is `sample`); string `batch_id` (required for all roles); optional `std_level` (required when `role` is `std` and the plate uses a standard-curve assay for that std well’s `assay_id`).

## Incident acceptance

An event is **accepted** when `kind` is exactly `lot_recall`, `day` ≤ `current_day`, `accepted` is not boolean `false`, and `lot_id` is a non-empty string present as a key under `lots.registry.json` (the registry file path in prose is `/app/labkit/lots/registry.json`; the JSON field is `lots`). Events with any other `kind`, with `day` > `current_day`, with `accepted` equal to boolean `false`, with missing/empty `lot_id`, or with unknown `lot_id` keys are **ignored** and increment the summary counter `ignored_incident_events`.

The **recalled lot set** is the sorted ascending list of `lot_id` strings from accepted `lot_recall` events.

## Plate blank effective value

For a plate, collect `raw_value` from wells whose `role` is `blank`. Let `blank_count` be the count. If `blank_count` ≥ `policy.min_blanks`, `blank_effective` is the median of those values (median of an even-sized multiset is the arithmetic mean of the two middle values after sorting). Otherwise `blank_effective` is `policy.fallback_blank_value`.

A plate **uses blank fallback** when `blank_count` < `policy.min_blanks`.

## Per-well preliminary net and flags

### Non-sample wells

Wells with `role` `blank` or `std` always emit `net_value` null, `normalization_mode` null, `disposition` `skipped_non_sample`, and `detail` as the empty string.

### Samples with recalled lots

If the well’s `lot_id` is in the recalled lot set: `net_value` is null regardless of mode, `normalization_mode` mirrors the assay’s configured mode string, `disposition` is `frozen_recall`, and `detail` is exactly `recall:<lot_id>` using the well’s literal `lot_id`.

### `to_blank_median` samples

Let `m` be the assay’s `normalization_mode` string (`to_blank_median`). `net_value` = `raw_value - blank_effective` for the host plate. If the plate uses blank fallback, `disposition` is `blank_degraded` and `detail` is `blank_fallback`; otherwise `disposition` is `ok` and `detail` is the empty string until the drift pass may change `disposition` to `drift_alert`.

### `to_standard_curve` samples

Consider std wells on the same `plate_id` sharing the same `assay_id`. Build pairs `(x, y)` where `y` is `raw_value` and `x` is `assays[assay_id].std_x_by_level[std_level]`. If there are fewer than two pairs, or all `x` are identical, every sample well on that plate for that `assay_id` receives `net_value` null, `disposition` `curve_unusable`, and `detail` `curve_unusable`. Otherwise fit the least-squares line `y = a*x + b` across the pairs (simple unweighted linear regression). If `a` is zero, treat as unusable with the same disposition. For each sample well on that plate with the same `assay_id`, define `net_value` = `(raw_value - b) / a`. Preliminary `disposition` is `ok` with empty `detail` unless blank fallback applies to **any** sample well on that plate for **any** assay (plate-level flag); when blank fallback is true, every **sample** well on that plate receives `blank_degraded` and `detail` `blank_fallback` even for standard-curve assays. Recalled lots still win over curve/blank outcomes.

Regression ties: sort pairs by `(x asc, y asc)` before feeding the regression. Use double-precision arithmetic; `net_value` must be rounded to four decimal places using IEEE round-half-to-even.

## Drift pass (batch + assay monitored row)

For each row in `batches/index.json`, the monitored pair is `(batch_id, assay_id)` from that row. Consider only wells with `role` `sample`, matching `batch_id` and `assay_id`, and whose preliminary disposition is exactly `ok`.

Let `current_day` come from `pool_state.json`. For every integer `d` with `d` < `current_day`, look across all plates with `run_day == d` and collect the multiset of `net_value` for wells matching the batch+assay filter and preliminary `ok`. If that multiset is non-empty, define `S(d)` as the median of those numbers (even-count median rule matches blanks). The **historic list** is `[ S(d) | d < current_day and S(d) defined ]` sorted ascending by `d`.

If the historic list is empty, the rollup entry has `historic_median_net` null, `drift_status` `no_history`, and `drift_delta` null.

Otherwise `historic_median_net` is the median of the historic list values (median of medians). For the current window (`run_day == current_day` from any plate), let `T` be the median of the same filtered wells on those plates. If no such wells exist, set `sample_median_net` null, `sample_count_used` 0, `drift_status` `insufficient_samples`, `drift_delta` null, and do not promote wells to `drift_alert`.

When `T` exists, set `sample_median_net` to `T`, `sample_count_used` to the count of contributing wells, `drift_delta` = `T - historic_median_net`. If the absolute value of `drift_delta` is strictly greater than `policy.drift_abs_threshold`, set `drift_status` to `drift_alert`; otherwise `stable`. When `drift_status` is `drift_alert`, every contributing well on plates with `run_day == current_day` for that batch+assay pair whose preliminary disposition was `ok` must have final `disposition` `drift_alert` and `detail` `drift_batch`.

Dispositions not listed as changing remain unchanged from preliminary results when drift does not fire. `frozen_recall`, `curve_unusable`, `blank_degraded`, and `skipped_non_sample` are never overwritten by drift.

## Outputs

### `well_results.json`

Top-level key `wells`: array sorted ascending by `well_key`, where `well_key` is `plate_id + ":" + well_id`.

Each object includes keys `well_key`, `plate_id`, `well_id`, `batch_id`, `assay_id` (null when skipped non-sample and assay absent), `normalization_mode`, `net_value`, `disposition`, `detail`.

### `batch_assay_rollup.json`

Top-level key `entries`: sorted ascending by `(batch_id, assay_id)`. Each object includes `batch_id`, `assay_id`, `lineage_id` (from the batch row), `sample_median_net`, `sample_count_used`, `historic_median_net`, `drift_delta`, `drift_status`.

### `curve_diagnostics.json`

Top-level key `plates`: array sorted by `(plate_id asc, assay_id asc)`. Include one object per `(plate_id, assay_id)` where the assay mode is `to_standard_curve` and the plate has at least one well referencing that assay. Fields: `plate_id`, `assay_id`, `pair_count`, `slope`, `intercept`, `usable` (boolean), `residual_max` (null when `usable` is false; otherwise max absolute residual across std pairs from the fitted line).

Slope and intercept are full-precision JSON numbers from the regression; residuals use the same rounding as sample `net_value` inputs to the regression (`raw_value` unrounded).

### `lot_disposition.json`

Top-level key `lots`: sorted by `lot_id`. Each object has `lot_id`, `recalled` boolean, `affected_wells` integer count of sample wells with that lot across all plates after incident filtering.

### `summary.json`

Include keys `current_day`, `plates_loaded` (count of plate files processed), `ignored_incident_events`, `recall_lot_count`, and `disposition_counts` object whose keys are exactly the set of disposition strings encountered in `well_results` mapped to integer counts.

## Canonical hashing note for implementers

Serialise inner structures with `json.dumps(..., sort_keys=True, separators=(",", ":"))` when byte-stable hashes are required by the verifier.
