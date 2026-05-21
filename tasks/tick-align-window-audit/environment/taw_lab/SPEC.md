# Tick align window audit

Normative contract for `/app/taw_lab/` plus three audit artifacts under `/app/audit/`.

## CLI layout

The entry binary reads `TAW_DATA_DIR` and `TAW_AUDIT_DIR` when `argc` is `1` (program name only), defaulting those variables to `/app/taw_lab` and `/app/audit` if unset. When `argc` is `3`, `argv[1]` is the lab root and `argv[2]` is the audit directory, overriding the environment variables. Any other argument count is invalid.

## Inputs

- `policy.json` fields (required, no extras): `window` (`start_day`, `end_day` inclusive integers), `anchors_path` (relative path under the lab root), `lanes_glob` (glob relative to lab root), `pool_state_path`, `incident_log_path`, `align_slack` (integer `>= 0`), `per_lane_cost` (integer `> 0`), `stride_sign_fold` (boolean).
- `anchors/<file>` per `anchors_path`; must contain `window` with the same shape as policy.
- `pool_state.json` via `pool_state_path` with integer `tokens` (`>= 0`).
- `incident_log.json` via `incident_log_path` with array `incidents` of objects `{lane_id, through_day}`.
- Lane files matched by `lanes_glob`, each `{lane_id, day_start, day_end, tick_base, tick_stride, tier}` with `day_start <= day_end`.

Reject inputs (process exits non-zero) when any required file is missing, any path would escape the lab root, `policy.window` or anchor `window` is inverted, or the intersection of `policy.window` and `anchors.window` is empty.

## Effective window

Let `eff_start = max(policy.window.start_day, anchors.window.start_day)` and `eff_end = min(policy.window.end_day, anchors.window.end_day)`. The effective window is `[eff_start, eff_end]` inclusive. Lanes intersect this window when `max(lane.day_start, eff_start) <= min(lane.day_end, eff_end)`.

## Lane tick at effective end

Let `ee = min(lane.day_end, eff_end)`. If the lane does not intersect the effective window, it is ignored for clustering and summaries except it still contributes nothing.

If intersecting, let `stride = lane.tick_stride`, and if `stride_sign_fold` is true replace `stride` with its absolute value. The lane tick at the effective end day is `lane.tick_base + stride * (ee - lane.day_start)`.

## Quarantine

If any incident has `through_day >= eff_start`, that `lane_id` is quarantined for the whole audit whenever the lane intersects the effective window. Quarantined lanes never merge with others.

## Clustering

Consider only lanes that intersect the effective window. Build undirected edges between non-quarantined lanes `p` and `q` when `abs(tick_p - tick_q) <= align_slack`. Connected components are clusters. Sort lanes inside a cluster by `(tick, lane_id)` ascending. Sort clusters by the minimum `lane_id` in the cluster ascending.

Emit clusters in this order: first every quarantined lane as its own cluster, sorted by `lane_id` ascending; then every merged cluster in the sorted cluster order above. Assign `cluster_id` as `0..n-1` in emission order.

Cluster `status` values:

- `quarantined` for singleton quarantine clusters (`pool_draw` is `0`).
- For other clusters, walk clusters in `cluster_id` ascending. Let `cost = per_lane_cost * len(lane_ids)`. If `tokens >= cost`, subtract `cost` from `tokens`, set `pool_draw = cost`, `status = pool_satisfied`. Otherwise set `pool_draw = 0`, `status = pool_deferred` without changing `tokens`.

## Outputs (UTF-8 JSON)

Write exactly three files under the audit directory: `clusters.json`, `pool_ledger.json`, `summary.json`.

### `clusters.json`

Top-level object with key `clusters` only: array of objects with keys `cluster_id` (int), `lane_ids` (array of strings sorted ascending), `ticks` (object mapping each lane id to its computed tick int), `pool_draw` (int), `status` (one of `quarantined`, `pool_satisfied`, `pool_deferred`).

### `pool_ledger.json`

Object with keys `draws`, `opening_tokens`, `closing_tokens`. `draws` is an array in chronological order of each successful draw with keys `after`, `amount`, `before`, `cluster_id` (all integers). `opening_tokens` is the starting pool. `closing_tokens` is the remaining pool after processing.

### `summary.json`

Object with keys: `closing_tokens`, `cluster_count`, `effective_window` (`start_day`, `end_day`), `lane_count_in_window` (lanes intersecting the effective window), `opening_tokens`, `pool_deferred_clusters`, `pool_satisfied_clusters`, `quarantined_clusters`, `stride_sign_fold_applied` (boolean echo of policy), `tiers_touched` (sorted unique list of `tier` strings for lanes that intersect the effective window).

## Canonical on-disk JSON

Every output file MUST match `json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True)` in Python semantics: two-space indent, ASCII-only strings, recursively sorted object keys at every depth, and exactly one trailing newline after the root closing brace.
