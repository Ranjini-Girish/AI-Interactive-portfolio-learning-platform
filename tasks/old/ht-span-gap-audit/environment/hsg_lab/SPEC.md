# Half-open span gap audit (normative)

All JSON must be UTF-8 without BOM. The audit writes `/app/hsg_audit/report.json` as pretty-printed JSON with two ASCII spaces per indent level, ASCII-only text, sorted object keys at every depth, comma+space after commas between values, colon+space after each colon, no trailing spaces on lines, and exactly one trailing newline after the closing brace.

## Inputs under `/app/hsg_lab/`

- `policy.json` with integer `merge_gap` (>=0). Two intervals `[lo,hi)` may merge when, after sorting by `lo` ascending and then `hi` ascending, the gap `next.lo - prev.hi` is less than or equal to `merge_gap` (touching intervals have gap 0).
- `pool_state.json` with integer `current_tick`.
- `incident_log.json` with `events` array. Each event has integer `apply_tick`, string `event_id`, string `kind`, and optional fields described below.
- `lanes/*.json` files whose basenames match `^[a-z0-9][a-z0-9_-]*\\.json$`, sorted by relative POSIX path. Each file contains `lane_id` (string) and `intervals` (array of objects with integer `lo` and `hi` with `lo < hi`).
- `anchors/` and `ancillary/` exist for packaging parity; the audit must not read them.

## Incident semantics

Sort events by `apply_tick` ascending, then `event_id` lexicographically. Let `events_seen` be the number of events in that sorted order. For each event in order:

- If `apply_tick > pool_state.current_tick`, ignore the event for mutations (but it still counts in `events_seen`).
- Otherwise consider it **honored**. Unknown `kind` increments `unknown_event_kinds` and does nothing else.
- `noop` does nothing.
- `drop_tick` requires `lane_id` and integer `tick`. Remove every raw interval on that lane where `lo <= tick < hi`. Removal happens before merges for that lane, but honored events apply in sorted order across the whole log, mutating the evolving lane maps between events.

## Merge semantics

For each lane independently, after all honored incidents, sort surviving intervals by `lo` then `hi`. Sweep merge: start stack with first interval; for each next interval, if `next.lo - stackTop.hi <= merge_gap`, set `stackTop.hi = max(stackTop.hi, next.hi)`; else push `next`. `merged_count` is the number of stack entries after the sweep. `covered_ticks` is the sum of `(hi - lo)` across those merged intervals.

## Output `/app/hsg_audit/report.json`

Top-level keys `lanes` then `summary` (ASCII key order).

Each `lanes` element has keys `covered_ticks`, `id`, `merged_count` (alphabetical order in output objects). `id` is the lane_id string. Sort the `lanes` array by `id` ascending.

`summary` keys alphabetical:

- `covered_ticks_total`: sum of per-lane `covered_ticks`.
- `events_seen`: defined above.
- `lanes_considered`: length of `lanes` array.
- `unknown_event_kinds`: count of honored events whose `kind` is neither `noop`, `drop_tick`, nor recognized (only those three are known besides unknown bucket).
