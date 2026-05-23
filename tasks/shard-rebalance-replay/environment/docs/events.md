# Event semantics

Events are processed in strict ascending `seq` order; `seq` values must be a
dense range `0..N-1`. Each event is one of seven operations. Within a single
event, at most one error code is emitted; multiple warnings and notes may be
emitted alongside it. The diagnostic priority order (most-severe-error wins)
is:

```
E_SHARD_NOT_FOUND  >  E_NODE_NOT_FOUND  >  E_DUPLICATE_NODE  >
E_REBALANCE_INFEASIBLE  >  E_NODE_BUSY
```

For the warning/note codes (`W_RACK_FALLBACK`, `W_REPLICA_DEMOTED`,
`N_SHARD_MOVED`) all that fire are emitted; they coexist with at most one
error code from the list above.

## node_join

Fields: `node_id`, `weight`, `rack`.

1. If `node_id` was ever observed (initial layout, prior `node_join`, or
   already left): emit `E_DUPLICATE_NODE` with `ref_id = node_id`. No state
   change.
2. Otherwise add the node as `active` with the supplied `weight` and `rack`.
   Increment `nodes_joined`.
3. If `policy.auto_rebalance_after_join` is true and at least one shard
   exists, run a rebalance round at this `seq` (see `rebalance.md`). Each
   resulting move uses `trigger = "auto_join"` in the move log and increments
   `auto_join_moves`.

## node_leave

Field: `node_id`.

1. If the node is not present (active or draining): emit `E_NODE_NOT_FOUND`
   with `ref_id = node_id`. No state change.
2. Otherwise enumerate every shard where the node is the `primary` or appears
   in `replicas`, in ascending shard-id order. For each such shard pick a
   substitute holder: the active, non-leaving node with the lowest current
   load (smaller `(total_bytes_held * other_weight)` cross-product against
   another candidate's `(other_total_bytes * weight)`), tie-broken by
   ASCII-smallest id, that is not already a holder of the shard.
3. If any shard has no eligible substitute, emit
   `E_REBALANCE_INFEASIBLE` once with `ref_id` set to the smallest-id
   infeasible shard, then abort the leave. The node remains in place.
4. Otherwise perform every move in shard-id order, replacing the leaving node
   with its substitute in the same role (`primary` or `replica`). For each
   move: if `policy.rack_awareness` is true and the substitute's rack matches
   the rack of any other holder of that shard after the move, emit
   `W_RACK_FALLBACK` with `ref_id = shard_id`; then emit `N_SHARD_MOVED` with
   `ref_id = shard_id`. Append to the move log with `trigger = "leave"`.
   Increment `auto_leave_moves` for each move.
5. Remove the node from the cluster. Increment `nodes_left`.
6. If `policy.auto_rebalance_after_leave` is true, run a follow-up rebalance
   round (`trigger = "auto_leave"`).

## node_drain

Field: `node_id`.

1. If the node is not present: emit `E_NODE_NOT_FOUND`.
2. If the node is already `draining`: emit `E_NODE_BUSY` with
   `ref_id = node_id`.
3. Otherwise mark the node `draining`. Increment `nodes_drained`.
4. For each shard (in ascending id order) where the draining node is the
   `primary` and at least one replica is currently held by an active
   (non-draining) node, promote the active replica with the lowest load
   (tie-break: ASCII-smallest id) to primary. The draining node becomes a
   replica. Append to the move log: `from = draining_node`,
   `to = promoted_replica`, `role = "primary"`, `trigger = "drain"`. Emit
   `W_REPLICA_DEMOTED` with `ref_id = node_id` (the draining node) once per
   such swap. Increment `drain_swaps` for each swap.

If the primary on the draining node has no active replica, the primary stays
on the draining node and no diagnostic is emitted for that shard.

## node_resume

Field: `node_id`.

1. If the node is not present: emit `E_NODE_NOT_FOUND`.
2. If the node is not currently `draining`: emit `E_NODE_BUSY`.
3. Otherwise mark the node `active`. No moves.

## manual_move

Fields: `shard_id`, `from_node`, `to_node`, `role` (one of `"primary"` or
`"replica"`).

Validation order (first failing check wins, no state change on failure):

1. `E_SHARD_NOT_FOUND` if `shard_id` is unknown.
2. `E_NODE_NOT_FOUND` if `from_node` is not a known cluster member.
3. `E_NODE_NOT_FOUND` if `to_node` is not a known cluster member
   (`ref_id = to_node`).
4. `E_NODE_BUSY` (`ref_id = shard_id`) if any of the following: `from_node`
   equals `to_node`; `role == "primary"` but `shard.primary != from_node`;
   `role == "replica"` but `from_node` is not in `shard.replicas`; `to_node`
   is already a holder of the shard (primary or in replicas); `to_node` is
   currently `draining`.

On success, replace `from_node` with `to_node` in the shard's holder set in
the same role. If `policy.rack_awareness` is true and the new holder's rack
matches the rack of any other current holder of the shard, emit
`W_RACK_FALLBACK` (`ref_id = shard_id`) before the success note. Emit
`N_SHARD_MOVED` (`ref_id = shard_id`). Append to the move log with
`trigger = "manual"`. Increment `manual_moves`.

## rebalance_round

No fields beyond `seq` and `op`.

Increment `rebalances` (always, even if no moves happen). Run the rebalance
algorithm in `rebalance.md` with `trigger = "rebalance"`. Each move emits
`N_SHARD_MOVED`, optionally preceded by `W_RACK_FALLBACK` per the algorithm,
and increments `rebalance_moves`.

## shard_resize

Fields: `shard_id`, `size_bytes` (positive integer).

1. If `shard_id` is unknown: emit `E_SHARD_NOT_FOUND`.
2. Otherwise update the shard's `size_bytes` to the new value. Increment
   `shard_resizes`.

This op never produces a move and never triggers a rebalance.
