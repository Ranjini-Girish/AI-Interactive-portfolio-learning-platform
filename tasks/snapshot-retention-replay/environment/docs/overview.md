# snapret -- overview

`snapret` is a deterministic snapshot-retention manager. It replays a
synthetic, dataset-scoped log of snapshot operations (creates, deletes,
holds, clock ticks, retention runs) and emits four canonical JSON
reports describing the final snapshot state, every retention decision,
the per-event diagnostic stream, and a counter summary.

## Inputs

All three input documents live under the data directory passed as
`argv[1]`. The simulator never writes to that directory.

- `snapshots.json` -- the initial per-dataset snapshot table.
- `events.json` -- a strictly increasing dense `seq` log of operations.
- `policy.json` -- global and per-dataset retention rules.

## Outputs

The four output documents are written to the directory passed as
`argv[2]`. Every file is canonical JSON: UTF-8, ASCII-only escapes,
two-space indent, lexicographically sorted object keys at every depth,
and a single trailing newline.

- `snapshot_state.json` -- the final per-dataset snapshot tables.
- `prune_log.json` -- chronological per-`retention_run` decisions.
- `retention_diagnostics.json` -- per-event diagnostics drawn only from
  the closed code set in `diagnostics.md`.
- `summary.json` -- counters and the sorted list of datasets still
  holding at least one snapshot at trace end.

The verifier reruns its own reference implementation against the same
data directory and compares the four outputs byte-for-byte against
yours. Hardcoded expected outputs will not match a different fixed
input set, and any deviation from the rules in this `docs/` tree will
surface as a byte diff.

## Time

There is a single integer clock, `now_sec`, seeded from
`policy.now_sec`. The clock advances **only** through `tick` events
with positive `delta_sec`. Every `snapshot_create` event timestamps the
new snapshot with the current value of `now_sec`.

## Dataset scoping

Snapshots are partitioned by their `dataset` field. The `(dataset,
name)` pair must be unique within a single dataset. Snapshot ids are
unique across all datasets.

## Determinism

All ordering decisions in `snapret` are total and deterministic. Where
two snapshots tie on `created_at_sec`, the tie is broken by snapshot
`id`. The algorithm is otherwise insensitive to map iteration order:
the implementation is free to use hash maps, ordered maps, or vectors
internally as long as the emitted JSON respects the documented sorts.
