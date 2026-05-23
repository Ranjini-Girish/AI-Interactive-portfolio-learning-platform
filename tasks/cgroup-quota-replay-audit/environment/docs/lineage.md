# Lineage Graph

`lineage_graph.json` records the directed graph induced by every
**successful** `move_subtree` event. The graph is empty (no nodes, no
edges, no cycles) when `policy.track_lineage` is false.

## Nodes

When `track_lineage` is true the node set contains every cgroup id that
ever appeared in the trace:

- every id from the initial `cgroups.json`,
- every id introduced by a successful `create`,
- every id used as `id` or `target_parent_id` by any **successful**
  `move_subtree` (which is always a subset of the above two -- you can
  only move an id that exists),
- every id deleted by a successful `delete` (it was a node before the
  delete, and deletion does not remove it from the lineage graph -- the
  graph is a history-of-the-trace artefact, not a live snapshot).

Diagnostic-emitting (failed) events do NOT contribute nodes from their
`id` / `target_parent_id` fields. A `move_subtree` that emitted
`E_CYCLE_REJECTED` or `E_PARENT_NOT_FOUND` adds nothing.

Each node carries `{ "id": <str>, "in_degree": <int>, "out_degree": <int> }`
computed from the **deduplicated** edge set.

## Edges

For every successful `move_subtree` event, add a directed edge

```
source_parent_id  ->  moved_cgroup_id
```

where `source_parent_id` is the cgroup's `parent_id` immediately BEFORE
the move (so a move from `null` -- i.e. the cgroup was at root -- adds an
edge from the literal string `"<root>"` to the moved id; `"<root>"` is
also added as a node when at least one such edge exists).

If a cgroup is moved more than once, every move adds its own edge
`prev_parent -> id` -- but the edge set is deduplicated by `(from, to)`,
so a cgroup that is moved between two parents `A` and `B` and back will
contribute the edges `A -> id` (from the first move out of `A`) and
`B -> id` (when it later leaves `B`); the edge `A -> id` does NOT appear
twice even if the cgroup is moved away from `A` more than once.

The literal target parent id (i.e. the new home) does NOT appear as the
`from` side of an edge for the same move. Lineage edges are always
"who used to own this" -> "who got moved", never "who got it now" ->
"who got moved".

`from == to` (a cgroup whose previous parent was itself) is impossible by
construction (a cgroup cannot be its own parent), so no self-loops can
arise; if the implementation accidentally produces one it must NOT be
emitted.

## Cycles

`cycles` lists every multi-vertex SCC of the lineage graph as its
sorted member ids (outer list sorted by lex-smallest member). A cycle of
size 1 (a self-loop) is suppressed by the no-self-loops rule above. A
cycle of size 2 arises when two cgroups have each been moved out from
under each other (e.g. `A` moves out of `B`, then later `B` moves out of
`A`).

`topological_layers` is NOT part of `lineage_graph.json` -- the lineage
graph is for history inspection, not for ordering anything.

## When `track_lineage` is false

`lineage_graph.json` is exactly:

```
{
  "cycles": [],
  "edges": [],
  "nodes": []
}
```

(formatted canonically: 2-space indent, trailing newline, sorted keys).
