# Lineage Graph

`lineage_graph.json` is a directed graph that records every parent-child
relationship that emerges during the trace, in two flavours:

- A **`"fork"`** edge `parent_pid -> child_pid` is added once per
  successful `fork` event. This edge points from the (then-RUNNING) parent
  to the freshly-created child.
- A **`"reparent_init"`** edge `init_pid -> child_pid` is added when an
  orphan reparent under `policy.orphan_handling == "reparent_to_init"`
  rewrites the child's `ppid` to `init_pid`.

A child that is reparented multiple times under different schemes can carry
both edge types simultaneously: one `"fork"` edge from its original parent,
and one `"reparent_init"` edge from `init_pid`. Edges of different types
between the same `(from, to)` pair are kept as distinct entries.

## Population gate

The graph is populated ONLY when `policy.track_lineage` is `true`. When
`track_lineage` is `false`, `lineage_graph.json` is exactly:

```
{
  "cycles": [],
  "edges": [],
  "nodes": []
}
```

regardless of any forks or reparents that happened in the trace.

## Nodes

When `track_lineage` is true, `nodes` carries one entry per pid that ever
appeared anywhere in the simulation - the union of:

- every initial pid in `processes.json`,
- every pid that was successfully created by a `fork` event,
- every pid that appears as a `from` or `to` in `lineage_graph.edges`
  (which is a subset of the above).

A pid that was named in an event but never created (e.g. a `fork` whose
`parent_pid` was missing, or a `wait` against an unknown pid) is NOT added
to `nodes` - those events are diagnostic-only and do not introduce new
processes.

Each node carries:

- `id` - the integer pid,
- `in_degree` - the count of distinct edges pointing INTO this pid (across
  both edge types),
- `out_degree` - the count of distinct edges pointing OUT of this pid
  (across both edge types).

`nodes` is sorted by `id` ascending.

## Edges

Each edge carries:

- `from` - the integer source pid,
- `to` - the integer destination pid,
- `type` - either `"fork"` or `"reparent_init"`.

Edges are deduplicated within a `(from, to, type)` triple: if the same
fork or reparent pattern would emit a duplicate, only one edge is recorded.
Distinct types between the same `(from, to)` pair count as distinct edges.
`edges` is sorted by `(from, to, type)` ascending.

## Cycles

`cycles` is the list of multi-vertex strongly connected components of the
directed graph induced by `edges`. A well-formed POSIX process tree never
produces a cycle (every fork strictly extends the tree, and reparenting
attaches an orphan to `init_pid` which has no outgoing edges that lead back
to it through forks). The field exists for symmetry with the other
graph-shaped outputs in this benchmark family and to defend against
exotic event sequences that might wedge a cycle in.

When non-empty, each inner list carries the SCC's member pids sorted
ascending. The outer list is sorted by the lex-smallest member of each
inner list. When `track_lineage` is false OR no SCC has more than one
member, `cycles` is `[]`.
