# Overview

This task asks you to build a deterministic replay engine for a
**Weighted Adaptive Replacement Cache** (W-ARC). W-ARC is a variant of
ARC (Megiddo and Modha) in which every access carries an integer
weight, resident entries carry a `cum_weight` accumulator, and the
REPLACE subroutine selects the **min-`cum_weight`** entry as the
victim (with LRU as tiebreak) instead of the strict LRU entry. All
other ARC invariants are preserved: four ordered lists T1, T2, B1,
B2; the adaptive parameter `p` is updated by the canonical ghost-hit
delta formula; and the population bounds `|T1|+|T2| <= c` and
`|T1|+|B1|+|T2|+|B2| <= 2c` are enforced after every operation.

## Binary contract

The binary is `arcache` and is invoked as:

```
arcache <in_dir> <out_dir>
```

Both arguments must be real directories (not symlinks). Sources live
under `/app/src` and headers under `/app/include`. The binary must be
rebuilt from those visible sources at solution time; its mtime must
be strictly newer than every visible source file. The compiled
binary must live at `/app/build/arcache`.

## Inputs

Two JSON files are read from `<in_dir>`:

* `events.json` -- the event log, in input order.
* `config.json` -- the cache size `c`.

See `schemas/events.schema.json` and `schemas/config.schema.json` for
the exact shape. Inputs that fail those schemas, that have extra
top-level keys, that have type mismatches, or that contain values
outside the documented ranges must cause the binary to abort with
non-zero exit before any output is written.

## Outputs

Five JSON files are written into `<out_dir>`:

* `cache_state.json`
* `decisions.json`
* `event_audit.json`
* `summary.json`
* `violations.json`

All five outputs are canonical JSON: UTF-8, ASCII-only `\uXXXX`
escapes, two-space indent, recursively sorted object keys at every
depth, and exactly one trailing newline. They are produced
atomically through `.partial` staging files; see `output_format.md`
for details.

## Determinism

Given the same `<in_dir>` and an empty `<out_dir>`, two invocations
of the binary must produce byte-identical files in `<out_dir>`.
There is no randomness, no external entropy source, and no time
source beyond the `ts_unix_ms` fields on events.
