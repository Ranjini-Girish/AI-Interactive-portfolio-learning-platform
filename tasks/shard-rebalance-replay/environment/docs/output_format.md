# Output formats

All five outputs are canonical JSON: UTF-8, ASCII-only, two-space indent,
lexicographically sorted object keys at every depth, and a single trailing
newline. Numeric values are integers (no floats). Replicas inside any output
shard record are listed ASCII-sorted.

## `cluster_state.json`

```
{
  "nodes": [
    {
      "id":            "n01",
      "owned_bytes":   <int>,
      "rack":          "<string>",
      "shard_count":   <int>,
      "status":        "active" | "draining",
      "weight":        <int>
    },
    ...
  ],
  "shards": [
    {
      "id":         "s01",
      "primary":    "<node_id>",
      "replicas":   ["<node_id>", ...],
      "size_bytes": <int>
    },
    ...
  ]
}
```

`nodes` is sorted ASCII by `id`. `shards` is sorted ASCII by `id`. Each
node's `owned_bytes` is the sum of `size_bytes` across every shard where it
appears as primary OR replica at trace end; `shard_count` is that count.
Removed nodes are excluded from `nodes`.

## `move_log.json`

```
{
  "moves": [
    {
      "from_node": "<node_id>",
      "role":      "primary" | "replica",
      "seq":       <int>,
      "shard_id":  "<shard_id>",
      "to_node":   "<node_id>",
      "trigger":   "manual" | "drain" | "leave" | "auto_join" | "auto_leave" | "rebalance"
    },
    ...
  ]
}
```

Entries are appended in chronological order and never sorted. Entries within
a single `seq` keep the order in which the simulator generated them (e.g.,
auto-join moves keep the rebalance algorithm's iteration order; leave-driven
moves are emitted in ascending shard-id order).

## `cluster_diagnostics.json`

```
{
  "events": [
    {
      "diagnostics": [
        {"code": "<CODE>", "ref_id": "<string>" | null, "severity": "error" | "warning" | "note"},
        ...
      ],
      "seq": <int>
    },
    ...
  ]
}
```

Only events that produced at least one diagnostic appear. `events` is sorted
ascending by `seq`. Within an event, diagnostics are sorted by
`(severity_rank, code, ref_id)` with `severity_rank = error:0, warning:1,
note:2` and a `null` `ref_id` treated as the empty string for sort purposes
only (the JSON value remains `null`).

## `move_graph.json`

See `lineage.md`. Shape:

```
{
  "cycles": [["<id>", ...], ...],
  "edges":  [{"from": "<id>", "to": "<id>"}, ...],
  "nodes":  [{"id": "<id>", "in_degree": <int>, "out_degree": <int>}, ...]
}
```

When `policy.track_history` is false, `cycles`, `edges`, and `nodes` are all
empty.

## `summary.json`

```
{
  "auto_join_moves":          <int>,
  "auto_leave_moves":         <int>,
  "drain_swaps":              <int>,
  "events_with_diagnostics":  <int>,
  "final_node_count":         <int>,
  "final_shard_count":        <int>,
  "manual_moves":             <int>,
  "nodes_drained":            <int>,
  "nodes_joined":             <int>,
  "nodes_left":               <int>,
  "racks":                    ["<rack>", ...],
  "rebalance_moves":          <int>,
  "rebalances":               <int>,
  "shard_resizes":            <int>,
  "total_events":             <int>
}
```

`racks` is the ASCII-sorted set of distinct racks among nodes still present
in the cluster at trace end. `events_with_diagnostics` equals
`len(cluster_diagnostics.events)`. `total_events` equals the number of
events read from `events.json`. `rebalances` counts every `rebalance_round`
event regardless of how many moves resulted; `rebalance_moves` counts moves
produced specifically by explicit `rebalance_round` events (auto-rebalance
moves are accounted in `auto_join_moves` / `auto_leave_moves`). The summary
keys are exactly the fifteen documented above; no extras, no omissions.
