# Rod pack void audit

Inputs live under the task data root (default `/app/rod_lat/`). JSON is UTF-8. Required files are listed below; optional keys are explicitly called out.

## Coordinates

`domain_layout.json` defines integer `domain_end` and a `cells` array. Each cell has `id`, `lo`, and `hi` with `0 <= lo < hi <= domain_end`. Cells are half-open spans `[lo, hi)`.

Every `cells/<id>.json` repeats `id` and lists `rods`. A rod is `{rod_id,a,b}` describing the half-open interval `[a,b)` with integers obeying `lo <= a < b <= hi`.

## Ghost layer

`policy.json` contains string `ghost_mode` equal to `omit` or `include`.

When `ghost_mode` is `include`, read `ancillary/ghost_rods.json` and append each object in its `additions` array to the working rod list of the named `cell_id` before incidents. When `ghost_mode` is `omit`, never read that ghost file for computation.

## Incident window

Read `pool_state.json` for integer `current_day`. Read `anchors/window.json` for integer `start_day`. Let `floor_day` equal `policy.incident_day_floor` when that key exists; otherwise use `start_day`.

An incident object is **eligible** when all are true:

- `kind` is `strip_rods` or `nudge_rods`.
- `day`, `event_id`, and `cell_id` exist. `day` is an integer with `floor_day <= day <= current_day`.
- For `strip_rods`, `rod_ids` exists and is a non-empty JSON array of strings.
- For `nudge_rods`, integer `delta` exists.

Everything else is **ignored** for processing but counted in `ignored_incidents`.

Eligible incidents are applied in ascending `(day, event_id)` order using UTF-8 `event_id` ordering.

### `strip_rods`

Remove every rod in `cell_id` whose `rod_id` is listed in `rod_ids`. Missing ids are ignored.

### `nudge_rods`

For every rod remaining in `cell_id`, replace `(a,b)` with `(a+delta, b+delta)`, then clamp into `[lo, hi)` without changing length when possible:

1. If `a < lo`, add `(lo - a)` to both endpoints.
2. If `b > hi`, subtract `(b - hi)` from both endpoints.
3. If still `a >= b` or `a < lo` or `b > hi`, delete the rod.

## Clusters

`policy.json` contains `clusters`, an ordered array. Each cluster has string `name` and `cell_ids`, a non-empty array of distinct ids that all appear in `domain_layout.json`.

For each cluster in file order:

- `span_lo` is the minimum `lo` among its cells; `span_hi` is the maximum `hi`.
- `span_len = span_hi - span_lo`.
- For every rod in every member cell after ghosting and incidents, clip to the cluster span: `sa = max(a, span_lo)` and `sb = min(b, span_hi)`. Keep a clipped segment only when `sa < sb`. Its length is `sb - sa`.
- Merge all clipped segments on the line by standard interval union. Let `occupied_len` be the total length after merging (integer).
- `void_ppm = ((span_len - occupied_len) * 1_000_000) / span_len` using truncating integer division toward zero. If `span_len` is zero (should not happen with valid data), emit `void_ppm` as `0`.
- `segments_used` counts clipped segments with positive length before the union step.

## Outputs

Write four UTF-8 JSON files under the audit root (default `/app/rod_audit/`):

1. `cluster_voids.json` with key `clusters` in the same order as `policy.clusters`. Each record: `name`, `span_lo`, `span_hi`, `span_len`, `occupied_len`, `void_ppm`, `segments_used`.
2. `cell_snapshots.json` with key `cells`, sorted by `cell_id` ascending. Each record lists `cell_id`, `lo`, `hi`, and `rods` sorted by `rod_id` ascending.
3. `incident_trail.json` with `applied` (eligible incidents in applied order, each including `event_id`, `day`, `kind`, and the payload fields that were present) and integer `ignored`.
4. `summary.json` with integers `clusters`, `applied_incidents`, `ignored_incidents`, string `ghost_mode_used` copied from `policy.ghost_mode`, and `weighted_void_ppm = sum(void_ppm_i * span_len_i) / sum(span_len_i)` using integer division after the sum, evaluated in cluster file order.

## Canonical JSON

Outputs use two-space indentation, ASCII only, sorted object keys at every level, no trailing spaces on lines, and a single trailing newline at EOF.
