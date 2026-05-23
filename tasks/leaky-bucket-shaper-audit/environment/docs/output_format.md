# Output format

Write exactly four files under `/app/output/`. Every file is canonical
JSON: UTF-8 ASCII, two-space indent, lex-sorted keys, no extra keys
beyond the documented set, single trailing `\n`. Reruns on identical
inputs are byte-identical.

## `bucket_state.json`

```
{
  "buckets": [
    {
      "bucket_id": <string>,
      "capacity_bytes": <int>,
      "current_bytes": <int>,
      "leak_bytes_per_tick": <int>
    }
  ]
}
```

Sorted by `bucket_id`.

## `admits.json`

```
{
  "admits": [
    {"bucket_id": <string>, "level_after": <int>,
     "seq": <int>, "size_bytes": <int>}
  ]
}
```

Sorted by `(seq, bucket_id)`. Empty (`{"admits": []}`) when
`policy.track_admits=false`.

## `shaper_diagnostics.json`

```
{ "diagnostics": [ ... see diagnostics.md ... ] }
```

## `summary.json`

```
{
  "admits_total": <int>,            # always counts even if track_admits=false
  "buckets_total": <int>,
  "current_bytes_total": <int>,     # sum across buckets at end of run
  "dropped_bytes_total": <int>,     # 0 when count_dropped_bytes=false
  "events_total": <int>,
  "max_seq": <int|null>,            # null only when no events
  "now_ticks_final": <int>,
  "overflow_drops_total": <int>     # always counts W_DROPPED_OVERFLOW
}
```
