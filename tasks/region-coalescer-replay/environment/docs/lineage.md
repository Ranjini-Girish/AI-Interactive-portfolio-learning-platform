# Lineage Graph (`region_graph.json`)

When `policy.track_history` is `true` the simulator records a directed graph
over every region id that has EVER existed in the trace (both in
`regions.json` and any id introduced by a successful `map` or `split` event).
Ids removed by `unmap`, replace-eviction, explicit `merge`, or auto-coalesce
still appear as nodes -- the graph is a record of the lifetime of the trace,
not the final state.

Edges:

- After a successful `split` of source `A` into surviving `A` plus new
  `target_id == B`, add the edge `A -> B`. (Only one edge per split;
  `A -> A` is never added.)
- After a successful explicit `merge` of `[X, Y]` into kept id `K` (with
  `K = min(X, Y)`), add edges from BOTH parents to the kept region:
  `X -> K` AND `Y -> K`. The self-loop `K -> K` is suppressed (the kept
  region is one of the parents); the only edge from a parent to itself is
  the loop, so that one is dropped.
- An auto-coalesce on `map` or `unmap` does NOT add lineage edges. The
  lineage graph captures explicit user intent (split/merge), not the
  simulator's bookkeeping.

Edges are deduplicated (`{from, to}` with no multi-edges) and sorted by
`(from, to)` ASCII. Nodes are emitted as `{id, in_degree, out_degree}` over
the deduplicated edge set, sorted by `id` ASCII. Cycles -- the multi-vertex
SCCs of the graph -- are surfaced in `cycles` (sorted ASCII inside, outer
list sorted by lex-smallest member). For a well-formed trace the graph is a
DAG and `cycles` is `[]`, but a buggy upstream input could produce cycles
and your tool must surface them rather than refuse to write the file.

When `policy.track_history` is `false`, emit the graph object with `nodes ==
[]`, `edges == []`, and `cycles == []` -- still write the file, still in
canonical form.
