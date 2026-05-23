# Rebalance algorithm

Every rebalance round (whether triggered automatically by `node_join` /
`node_leave`, or by an explicit `rebalance_round` event) follows the same
deterministic procedure. The strategy is `"greedy_weight"` (it is the only
supported strategy in this simulator).

## Load score

For an active node `n`, define
`load(n) = sum of size_bytes for every shard where n is primary or replica`.

The "load score" used for ranking is the rational `load(n) / weight(n)`. To
avoid floating-point in the simulator, comparisons are done by
cross-multiplication on integers: `load(a) / weight(a)  >  load(b) / weight(b)`
iff `load(a) * weight(b) > load(b) * weight(a)`.

## Round procedure

For up to `policy.max_moves_per_round` iterations:

1. Build the active-node list (`status == "active"`), sorted ASCII by id.
2. If there are fewer than two active nodes, stop.
3. Pick `M` = the active node with the highest load score (tie-break:
   ASCII-smallest id) and `L` = the active node with the lowest load score
   (tie-break: ASCII-smallest id).
4. If `M == L`, stop.
5. If `load(M) * weight(L)  <=  load(L) * weight(M)` (i.e. `L` is not
   strictly less loaded than `M`), stop.
6. Build the candidate-shard list: shards where `M` is the primary or appears
   in the replicas, AND `L` is not a current holder. Sort the candidates by
   `(-size_bytes, shard_id)` (largest first; ties broken by ASCII-smallest
   shard id).
7. If the candidate list is empty, stop.
8. Pick the chosen shard:
   - If `policy.rack_awareness` is false, take the first candidate.
   - If `policy.rack_awareness` is true, walk the candidate list and take the
     first shard for which moving to `L` does NOT place two holders in the
     same rack (i.e. the rack of `L` does not appear among the racks of the
     remaining holders, where "remaining holders" means the shard's holders
     minus `M`). If every candidate violates the rack rule, take the first
     candidate (largest size, then ASCII-smallest id) and emit
     `W_RACK_FALLBACK` once with `ref_id = shard_id`.
9. Determine `role`: `"primary"` if `M` is the shard's current primary,
   otherwise `"replica"`.
10. Perform the move: replace `M` with `L` in the shard's holder set in the
    same role. Replicas are kept ASCII-sorted in the in-memory state.
11. Emit `N_SHARD_MOVED` with `ref_id = shard_id`. Append to the move log
    with the round's `trigger` ("auto_join", "auto_leave", or "rebalance").
12. Continue to the next iteration.

The round always stops once `max_moves_per_round` moves have been performed
or any of the early-exit checks (steps 2, 4, 5, 7) fires.
