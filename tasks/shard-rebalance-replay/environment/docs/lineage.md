# Move-lineage graph

`move_graph.json` records how shards have flowed across cluster nodes during
the trace, summarised at the node level. The graph is populated only when
`policy.track_history` is true; otherwise all three of its arrays
(`cycles`, `edges`, `nodes`) are empty.

## Construction

When `track_history` is true:

1. **Nodes.** The set of graph nodes is every `id` ever observed in the
   trace: every initial node id, every `node_join` event's `node_id`, and
   every `from_node` / `to_node` referenced by a successful `manual_move`,
   `node_drain` swap, `node_leave` reassignment, or rebalance move. Nodes
   are listed sorted ASCII by id; each entry carries `id`, `in_degree`,
   `out_degree`.
2. **Edges.** For every successful move (any `trigger`), insert the directed
   edge `(from_node, to_node)` into the lineage edge set. The set is
   deduplicated: the same `(from, to)` pair caused by multiple shards or
   multiple rounds appears once. Edges are emitted as
   `[{"from": ..., "to": ...}]` sorted lexicographically by `(from, to)`.
3. **Cycles.** Compute the directed graph's strongly-connected components
   over `(nodes, edges)`. Emit only the multi-vertex SCCs (more than one
   member). Each SCC is itself emitted as an ASCII-sorted list of member
   ids; the outer list of cycles is sorted by the smallest member id of
   each cycle.

A single self-loop (from == to) is impossible because every move replaces
one holder with a different node.

## Empty-history mode

When `track_history` is false, `move_graph.json` is exactly:

```
{
  "cycles": [],
  "edges": [],
  "nodes": []
}
```

The simulator must not infer the graph fields from prior runs or from
`cluster_state.json`; the policy flag is the single source of truth.
