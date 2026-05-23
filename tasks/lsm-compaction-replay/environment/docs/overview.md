# Overview

This task implements a deterministic **LSM-tree segment compaction
replay engine**. It reads a trace of `flush_memtable` and `compact`
events and produces five canonical JSON outputs describing every
segment that ever existed, every compaction decision, every input
event, and aggregate statistics.

## Layout

- `/app/data/events.json` — replay event log (`events` array).
- `/app/data/config.json` — `now_unix_ms` (informational only),
  `max_level`, `compaction_min_segments`.
- `/app/docs/` — full spec.
- `/app/schemas/` — JSON Schema for inputs and outputs.
- `/app/examples/input/` and `/app/examples/output/` — a minimal example.

## CLI contract

```
/app/build/lsmcompact <in_dir> <out_dir>
```

Compile from `/app/src/*.cpp` (+ `/app/include/`) with `g++ -std=c++17`.
The verifier rebuilds from source before every run, so a pre-baked
binary is rejected.

## Outputs

Exactly five files written under `argv[2]`, no symlinks, no extras:

- `segment_states.json`
- `compact_decisions.json`
- `event_audit.json`
- `violations.json`
- `summary.json`

All five are canonical JSON: `json.dumps(obj, indent=2, sort_keys=True,
ensure_ascii=True) + "\n"`. UTF-8 bytes that are ASCII-only at the
file-byte level, two-space indent, sorted keys at every depth, single
trailing newline.

## Determinism

Two consecutive runs over the same inputs must produce byte-identical
outputs. Do not seed anything from time-of-day, PID, hashmap iteration
order, or any other ambient source.

## Atomic writes

Stage each output to a sibling temporary path (e.g.
`name.json.partial`) and rename each into place only after every
output has been written. Refuse to overwrite a pre-existing entry at
any of the five output names. On any failure remove the staged
temporaries and any already-renamed siblings before exiting non-zero.

## `now_unix_ms`

`config.now_unix_ms` is informational only. It must not appear in any
output and it must not affect any decision.
