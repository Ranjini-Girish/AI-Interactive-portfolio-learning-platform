# Output format

All output files are **canonical JSON**:

```
json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
```

UTF-8 bytes that are ASCII-only at the file-byte level, two-space
indent, sorted keys at every depth, single trailing newline.

## `segment_states.json`

```json
{
  "segments": [
    {
      "seg_id": "s_0001",
      "level": 0,
      "size_bytes": 1024,
      "created_at_unix_ms": 1700000000000,
      "status": "merged",
      "merged_at_unix_ms": 1700000000500,
      "merged_into_event_id": "e_0005"
    }
  ]
}
```

- `status` ∈ `{"live","merged"}`.
- `merged_at_unix_ms` is null when `status == "live"`, else integer.
- `merged_into_event_id` is null when `status == "live"`, else the
  `event_id` of the `compact` event that merged it.
- Sorted ascending by `seg_id`.
- Every segment ever created (both live and merged) is included.

## `compact_decisions.json`

```json
{
  "decisions": [
    {
      "event_id": "e_0005",
      "ts_unix_ms": 1700000000500,
      "level": 0,
      "input_seg_ids": ["s_0001", "s_0002", "s_0003"],
      "output_seg_id": "merged_e_0005",
      "output_level": 1,
      "total_bytes": 3072
    }
  ]
}
```

- One entry per accepted `compact` event, in **input order**.
- `input_seg_ids` is sorted ascending and lists every segment merged.
- `output_seg_id` is the new segment created at `output_level`.
- `total_bytes` is the sum of input segment sizes.

## `event_audit.json`

```json
{
  "events": [
    {
      "event_id": "e_0001",
      "ts_unix_ms": 1700000000000,
      "type": "flush_memtable",
      "payload": {"seg_id": "s_0001", "size_bytes": 1024},
      "accepted": true,
      "reason_ignored": "none"
    }
  ]
}
```

- One entry per input event, sorted ascending by `event_id`.
- `accepted` is `true` for events that changed engine state.
- `reason_ignored` ∈
  `{"none","duplicate_seg_id","level_out_of_range","top_level_compaction","level_below_threshold"}`.

## `violations.json`

The subset of `event_audit.json` entries with `accepted == false`,
sorted ascending by `event_id`, with the same keys.

## `summary.json`

```json
{
  "total_events": 12,
  "total_flushes_accepted": 6,
  "total_compactions_accepted": 2,
  "total_segments_ever": 8,
  "live_segment_count": 4,
  "merged_segment_count": 4,
  "events_accepted": 8,
  "events_rejected": 4,
  "per_level_live_counts": {
    "0": 2,
    "1": 1,
    "2": 1
  }
}
```

- `per_level_live_counts` contains every level from 0 through
  `max_level` (decimal string keys). Object keys are
  lexicographically sorted in canonical JSON.
