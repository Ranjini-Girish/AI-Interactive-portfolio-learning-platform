# output_format.md -- canonical JSON shapes

Every output file under `argv[2]` must be canonical JSON: UTF-8,
ASCII-only escapes (the JSON `ensure_ascii=true` form), two-space
indentation, lexicographically sorted object keys at every depth, and
a single trailing `\n`. The verifier compares your outputs to a
reference impl byte-for-byte.

The matching JSON Schemas sit in `/app/schemas/`. The structural
example outputs in `/app/examples/sample_*.json` are derived from
`/app/examples/minimal_*.json` and are themselves canonical, so you
can use them to sanity-check your own dumper.

## `snapshot_state.json`

```
{
  "datasets": [
    {
      "name": <string>,
      "snapshots": [
        {
          "created_at_sec": <int>,
          "holders": [<string>, ...],
          "id": <string>,
          "name": <string>
        },
        ...
      ]
    },
    ...
  ]
}
```

- `datasets[]` is sorted by `name` ascending. A dataset only appears
  if it currently has at least one snapshot.
- `snapshots[]` within each dataset is sorted by `(created_at_sec
  asc, id asc)`.
- `holders[]` within each snapshot is sorted ASCII ascending. The
  array is always present, even when empty.

## `prune_log.json`

```
{
  "runs": [
    {
      "dataset": <string>,
      "kept": [
        {
          "id": <string>,
          "kept_by": [<string>, ...],
          "name": <string>
        },
        ...
      ],
      "pruned": [
        { "id": <string>, "name": <string> },
        ...
      ],
      "seq": <int>
    },
    ...
  ]
}
```

- `runs[]` is in chronological order (the order the `retention_run`
  events fired).
- Within a single run, `kept[]` is sorted by `(created_at_sec desc,
  id desc)` and `pruned[]` is sorted by `id asc`.
- `kept_by[]` is sorted ASCII ascending; possible values are
  `held`, `keep_daily`, `keep_hourly`, `keep_last_n`,
  `keep_monthly`, `keep_weekly`. A snapshot kept solely because a
  hold prevented its prune has `kept_by = ["held"]`.

## `retention_diagnostics.json`

```
{
  "events": [
    {
      "diagnostics": [
        {
          "code": <string>,
          "severity": "error" | "warning" | "note",
          "snapshot_id": <string|null>
        },
        ...
      ],
      "seq": <int>
    },
    ...
  ]
}
```

See `diagnostics.md` for sorting rules and the closed code set.

## `summary.json`

```
{
  "datasets_with_snapshots": [<string>, ...],
  "events_with_diagnostics": <int>,
  "final_snapshot_count": <int>,
  "retention_runs_executed": <int>,
  "snapshots_created": <int>,
  "snapshots_deleted_explicitly": <int>,
  "snapshots_pruned_by_retention": <int>,
  "total_events": <int>
}
```

- `datasets_with_snapshots` is the sorted ASCII list of dataset names
  that still contain at least one snapshot at trace end.
- `events_with_diagnostics` is the cardinality of
  `retention_diagnostics.events[]`.
- `total_events` is the length of `events.json.events[]`.
- The four counter fields are incremented as documented in
  `events.md`.
