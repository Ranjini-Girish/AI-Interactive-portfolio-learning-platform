# shardsim overview

`shardsim` is a deterministic C++17 simulator that replays a synthetic
shard-placement trace for a sharded data store. The model is a small cluster of
weighted, rack-tagged nodes that own data shards (each with one primary holder
and zero or more replica holders). The trace mutates the cluster topology and
the placement of shards over time, and the simulator records the resulting
state, the chronological move log, per-event diagnostics, and a node-to-node
lineage graph of how shards have flowed across nodes.

## Inputs

- `nodes.json`   — initial cluster topology (id, weight, rack) for the
  cluster's starting nodes.
- `shards.json`  — initial shard layout (id, primary, replicas, size_bytes).
  Replicas are an ASCII-sorted list of node ids, are pairwise distinct, and do
  not include the primary.
- `events.json`  — strictly increasing dense `seq` log of operations
  (`node_join`, `node_leave`, `node_drain`, `node_resume`, `manual_move`,
  `rebalance_round`, `shard_resize`). See `events.md`.
- `policy.json`  — tunables that select the rebalance strategy, the
  rack-awareness mode, and the lineage-tracking flag. The
  `replication_factor` field is informational only (recorded in inputs for
  context); the simulator does not enforce a target replica count and
  never adds or removes replicas to "fix" a shard whose holder count
  diverges from the policy value.

## Outputs

- `cluster_state.json` — final node + shard layout, both sorted by `id`.
- `move_log.json`      — every shard relocation that actually happened, in
  chronological order, with the trigger that caused it.
- `cluster_diagnostics.json` — per-event diagnostics, drawn from a closed code
  set, sorted within each event by `(severity_rank, code, ref_id)`.
- `move_graph.json`    — node-to-node DAG of shard movements, populated only
  when `policy.track_history` is true.
- `summary.json`       — documented counters plus the sorted ASCII list of
  racks present at trace end.

See `events.md`, `rebalance.md`, `diagnostics.md`, `lineage.md`, and
`output_format.md` for the per-concept rules.
