# State machine

## Per-segment state

A segment is created at level `L` with a size in bytes; it begins
`live`; it may transition to `merged` exactly once (by an accepted
`compact` event whose target level matches).

- `seg_id` — unique across all segments (flushed and merged).
- `level` — non-negative integer, fixed at creation.
- `size_bytes` — non-negative integer, fixed at creation.
- `created_at_unix_ms` — set to the creating event's `ts_unix_ms`.
- `status` — `live` then optionally `merged`.
- `merged_at_unix_ms` — null until merged.
- `merged_into_event_id` — null until merged.

## Event classification (in input order)

### `flush_memtable` (payload: `{seg_id, size_bytes}`)

1. `seg_id` collides with any previously declared segment (flushed or
   merged) -> **rejected**, `reason_ignored="duplicate_seg_id"`.
2. otherwise **accepted**: a new live segment is created at level 0
   with `size_bytes` from the payload and
   `created_at_unix_ms = ts_unix_ms`.

### `compact` (payload: `{level}`)

1. `level > max_level` -> **rejected**,
   `reason_ignored="level_out_of_range"`.
2. `level == max_level` -> **rejected**,
   `reason_ignored="top_level_compaction"` (there is no `level+1`).
3. fewer than `compaction_min_segments` live segments at the target
   level -> **rejected**,
   `reason_ignored="level_below_threshold"`.
4. otherwise **accepted**. Gather all live segments at the target
   level sorted by `seg_id` ascending. Mark each as `merged` with
   `merged_at_unix_ms = ts_unix_ms` and `merged_into_event_id = event_id`.
   Create a new live segment at `level+1` with
   `seg_id = "merged_" + event_id`, `size_bytes = sum(inputs)`,
   `created_at_unix_ms = ts_unix_ms`.

## End of replay

No implicit compactions occur. Whatever segments are live at end of
replay remain live.

## Decision rows

Each accepted `compact` event produces one row in
`compact_decisions.json` describing the inputs and the output. Rejected
`compact` events do not appear in `compact_decisions.json`.
