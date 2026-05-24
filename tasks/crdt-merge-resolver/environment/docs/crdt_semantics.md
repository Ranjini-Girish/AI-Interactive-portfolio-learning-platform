# CRDT Merge Semantics

## Vector Clock Comparison

A vector clock V1 **happens-before** V2 (written V1 → V2) if and only if:
- For ALL replica IDs r: V1[r] <= V2[r], AND
- For AT LEAST ONE replica ID r: V1[r] < V2[r]

Missing entries in a vector clock are treated as 0.

Two operations are **concurrent** if neither happens-before the other.

## Lamport Timestamp Ordering

When a total order is needed (for merge ordering and LWW resolution), operations
are sorted by:

1. **Lamport timestamp** ascending (lower = earlier)
2. **Replica ID** ascending lexicographic (tie-breaker when Lamport timestamps are equal)
3. **Op ID** ascending lexicographic (tie-breaker when replica IDs are also equal)

## Last-Writer-Wins (LWW) Register

For each key, the final value is determined by the operation with the
**highest** Lamport timestamp. If two operations on the same key have the
same Lamport timestamp, the operation from the replica with the
**lexicographically greater** replica ID wins (higher ID = later writer).

Note: the LWW winner uses the OPPOSITE tie-breaking direction from the merge
sort order. In merge order, lower replica ID comes first. In LWW, higher
replica ID wins.

## Tombstone Semantics

A DELETE operation sets the value to the tombstone marker (`__TOMBSTONE__`).
A tombstoned key is considered deleted and must NOT appear in the final state.

### Resurrection

If a SET operation has a higher Lamport timestamp than the most recent DELETE
for the same key, the key is "resurrected." The final state includes the
resurrected value. Each resurrection must be recorded as an anomaly.

## Per-Key Operation History

For each key in the merged log, compute:
- `write_count`: total number of operations (SET + DELETE) on this key
- `conflict_count`: number of pairs of concurrent operations on this key
- `final_op_id`: the op_id of the LWW-winning operation
- `final_value`: the value from the winning operation (null if tombstoned)
- `is_tombstoned`: true if the final state is a tombstone

## State Hash

Compute a SHA-256 hash of the final state (after all merges). The hash input
is constructed as follows:

1. Collect all non-tombstoned keys and their final values
2. Sort keys lexicographically ascending
3. Build a string: `key1=value1\nkey2=value2\n...keyN=valueN\n`
4. Each line ends with `\n` (including the last line)
5. Compute SHA-256 of the UTF-8 encoding of this string
6. Encode as lowercase hexadecimal
