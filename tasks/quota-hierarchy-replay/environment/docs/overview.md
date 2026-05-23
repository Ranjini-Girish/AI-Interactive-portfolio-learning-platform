# Hierarchical Quota Replay — Overview

This task replays a deterministic hierarchical resource-quota engine. You
are given a rooted tree of **namespaces** (each carrying its own
`{cpu, memory, storage}` limits), a linear stream of **allocate / release
events** targeting individual namespaces, and a small **config**. For
every event you decide whether to admit it (resources fit within every
ancestor's limits up to and including the root), reject it (limit
breach, unknown namespace, release underflow), or ignore it (release
against an unknown namespace under the lenient policy).

## File layout

* `/app/data/namespaces.json` — namespace tree (flat list with `parent`
  pointers)
* `/app/data/allocations.json` — ordered allocate / release events
* `/app/data/config.json` — global knobs (`now_unix_ms`,
  `release_unknown_action`)
* `/app/docs/` — full specification (this file, `tree.md`,
  `decisions.md`, `output_format.md`, `malformed_input.md`)
* `/app/schemas/` — JSON Schema definitions for every input and output
* `/app/examples/` — minimal end-to-end example (input + expected
  output, byte-identical to what your binary should emit)

## Required outputs (under `argv[2]`)

* `allocation_decisions.json` — per-event decision
* `namespace_usage.json` — per-namespace own + subtree usage summary
* `rollup_tree.json` — depth-first pre-order tree with cumulative
  subtree usage at every node
* `violations.json` — every event whose decision is `rejected`
* `summary.json` — global totals and `hottest_namespace`

All five files are canonical JSON (see `output_format.md`).

## Determinism

The reference simulator processes events strictly in the order they
appear under `allocations.events`. Namespaces are consumed in
declaration order for tree-building. `rollup_tree.json` visits children
in alphabetical order, making the traversal output fully deterministic
regardless of input ordering. No timestamps, sleeps, or RNGs are
consulted — `ts_unix_ms` is recorded for audit only.

## Informational config fields

`config.now_unix_ms` is parsed and validated (must be a non-negative
integer) but is **not** consulted during evaluation. It is captured for
audit-log alignment. Implementations MUST still reject the input when
`now_unix_ms` is missing, non-integer, or negative.

## Atomic output writes

The five output files MUST be staged so that either every file is
present in `argv[2]` after a successful run, or none of them are after
a failed run. The reference implementation writes each output to a
`<name>.partial` sibling first and renames into place only after all
five staging files have been written successfully; on any failure it
removes all staging files and any partially committed final files
before exiting non-zero.
