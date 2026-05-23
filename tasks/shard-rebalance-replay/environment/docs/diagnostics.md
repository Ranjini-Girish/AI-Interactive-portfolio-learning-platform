# Diagnostic codes

The simulator emits diagnostics drawn from the closed code set below. Any
other code in `cluster_diagnostics.json` is a spec violation. Within a single
event, diagnostics are sorted by `(severity_rank, code, ref_id)` where
`severity_rank` is `error=0`, `warning=1`, `note=2`, and a `null` `ref_id` is
treated as the empty string for sort purposes only. Each event emits at most
one error code (the most-severe per the priority chain in `events.md`).

## Code table

| Code                    | Severity | Meaning                                                                                                  |
|-------------------------|----------|----------------------------------------------------------------------------------------------------------|
| `E_DUPLICATE_NODE`      | error    | A `node_join` referenced an `id` that has already been observed in this trace (initial layout or prior). |
| `E_NODE_NOT_FOUND`      | error    | An event referenced a node id that is not currently a member of the cluster.                             |
| `E_SHARD_NOT_FOUND`     | error    | An event referenced a shard id that does not exist in the current shard set.                             |
| `E_REBALANCE_INFEASIBLE`| error    | A `node_leave` could not find a substitute for at least one shard the leaving node held.                 |
| `E_NODE_BUSY`           | error    | A move/drain/resume request was rejected because the node or shard role state already conflicts.         |
| `W_RACK_FALLBACK`       | warning  | A move proceeded even though the destination's rack already appears among the shard's other holders.    |
| `W_REPLICA_DEMOTED`     | warning  | A `node_drain` swapped a primary off the draining node onto an active replica.                            |
| `N_SHARD_MOVED`         | note     | A shard was relocated (via manual move, drain swap, leave-driven reassignment, or rebalance round).      |

## ref_id field

Every diagnostic carries a `ref_id` (string or null) chosen as follows:

- `E_DUPLICATE_NODE`        — the offending `node_id`.
- `E_NODE_NOT_FOUND`        — the missing node id (the field that referenced
  it; for `manual_move` validation, it is whichever of `from_node`/`to_node`
  is missing, in the documented validation order).
- `E_SHARD_NOT_FOUND`       — the missing `shard_id`.
- `E_REBALANCE_INFEASIBLE`  — the smallest-id shard that has no substitute
  candidate.
- `E_NODE_BUSY`             — the `node_id` for `node_drain`/`node_resume`
  conflicts; the `shard_id` for `manual_move` conflicts.
- `W_RACK_FALLBACK`         — the `shard_id` whose move forced the fallback.
- `W_REPLICA_DEMOTED`       — the `node_id` of the draining node (one note
  per shard whose primary was moved off it).
- `N_SHARD_MOVED`           — the `shard_id` that moved.
