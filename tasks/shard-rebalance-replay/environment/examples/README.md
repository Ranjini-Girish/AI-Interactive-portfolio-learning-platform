# shardsim examples

The `minimal_*.json` files together describe a small canonical input that a
correct `shardsim` produces the `sample_*.json` outputs from. They are not
the verifier dataset (those live under `/app/data/`), they are here so you
can sanity-check the field shapes without re-reading the docs.

## Scenario

Three nodes (`node-a`, `node-b`, `node-c`) on three different racks, one
shard with primary `node-a` and a single replica on `node-b`. A single
`manual_move` event swaps the primary onto `node-c`.

## Sanity check

After you have built `/app/build/shardsim`, you can run it against a
private copy of these example inputs to confirm shapes:

```
mkdir -p /tmp/shardsim_example
cp /app/examples/minimal_*.json /tmp/shardsim_example/
mv /tmp/shardsim_example/minimal_nodes.json    /tmp/shardsim_example/nodes.json
mv /tmp/shardsim_example/minimal_shards.json   /tmp/shardsim_example/shards.json
mv /tmp/shardsim_example/minimal_events.json   /tmp/shardsim_example/events.json
mv /tmp/shardsim_example/minimal_policy.json   /tmp/shardsim_example/policy.json
mkdir -p /tmp/shardsim_example/out
/app/build/shardsim /tmp/shardsim_example /tmp/shardsim_example/out
diff /tmp/shardsim_example/out/cluster_state.json /app/examples/sample_cluster_state.json
```

The five `sample_*.json` files are the exact byte-for-byte output the
reference produces for these inputs.
