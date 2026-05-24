# Merge Protocol

## Input Format

Each file under `/app/data/replicas/` is a JSON object with:
- `replica_id`: string identifier for the replica node
- `operations`: array of operation objects

Each operation has:
- `op_id`: globally unique string
- `key`: the data key being written
- `value`: string value (or `__TOMBSTONE__` for deletes)
- `op_type`: "SET" or "DELETE"
- `lamport_ts`: integer Lamport timestamp
- `vector_clock`: object mapping replica_id → integer counter
- `wall_clock_ms`: integer wall-clock timestamp in milliseconds

## Merge Process

1. **Load** all replica log files from `/app/data/replicas/`
2. **Collect** all operations from all replicas into a single list
3. **Sort** operations into total order using Lamport timestamp ordering
   (see crdt_semantics.md)
4. **Detect anomalies** (see Anomaly Detection below)
5. **Resolve** final state for each key using LWW semantics
6. **Compute** per-key statistics
7. **Compute** state hash
8. **Write** the merge report

## Anomaly Detection

### causal_violation

A causal violation occurs when operation B's vector clock indicates it
causally depends on operation A (A happens-before B), but B's wall clock
is EARLIER than A's wall clock by more than `max_clock_drift_ms`.

For each pair of operations (A, B) where A → B (A happens-before B):
- If B.wall_clock_ms < A.wall_clock_ms - max_clock_drift_ms, record a
  causal_violation anomaly.

Only check pairs where A and B operate on the SAME key.

### concurrent_write

Two operations on the same key are concurrent if neither happens-before
the other (based on vector clocks). Each unordered pair of concurrent
operations on the same key generates one concurrent_write anomaly.

### resurrection

A resurrection occurs when a key that was tombstoned (DELETE) is later
written with a SET that has a higher Lamport timestamp. The SET operation
that resurrects the key generates one resurrection anomaly.

### clock_regression

A clock regression occurs when a single replica issues operations where
the wall_clock_ms goes backwards. For each replica, sort its operations
by the order they appear in the log. If operation[i+1].wall_clock_ms <
operation[i].wall_clock_ms, record a clock_regression anomaly.

## Conflict Count

For each key, the conflict count is the number of UNORDERED pairs of
concurrent operations. If a key has 3 mutually concurrent operations,
the conflict count is 3 (= C(3,2) = 3 choose 2).

## Output Schema

```json
{
  "metadata": {
    "total_replicas": <int>,
    "total_operations": <int>,
    "replica_ids": [<sorted list of replica ID strings>],
    "unique_keys": <int>
  },
  "merged_log": [
    {
      "op_id": "<string>",
      "key": "<string>",
      "value": "<string>",
      "op_type": "<SET|DELETE>",
      "lamport_ts": <int>,
      "replica_id": "<string>",
      "vector_clock": {<string: int>},
      "wall_clock_ms": <int>
    }
  ],
  "key_states": [
    {
      "key": "<string>",
      "final_value": "<string or null>",
      "final_op_id": "<string>",
      "is_tombstoned": <bool>,
      "write_count": <int>,
      "conflict_count": <int>
    }
  ],
  "anomalies": [
    {
      "type": "<anomaly_type>",
      "description": "<human-readable description>",
      "op_ids": [<list of involved op_id strings, sorted>],
      "key": "<affected key or null>"
    }
  ],
  "summary": {
    "total_anomalies": <int>,
    "anomalies_by_type": {
      "causal_violation": <int>,
      "concurrent_write": <int>,
      "resurrection": <int>,
      "clock_regression": <int>
    },
    "total_keys": <int>,
    "tombstoned_keys": <int>,
    "active_keys": <int>,
    "total_conflicts": <int>,
    "state_hash": "<sha256 hex string>"
  }
}
```

## Convergence Metrics

Compute the following metrics and include them in the `convergence` section:

### causal_depth

For each key, compute the **longest causal chain length**. A causal chain
is a sequence of operations op1, op2, ..., opN on the same key where each
op[i] happens-before op[i+1]. The causal depth is the length of the longest
such chain (number of operations in the chain, NOT number of edges).

Report:
- `max_causal_depth`: the maximum causal depth across all keys
- `avg_causal_depth`: the average causal depth across all keys (6 decimal places)
- `per_key`: object mapping key -> causal_depth (sorted by key)

### stability_score

For each key, determine if the LWW winner is "stable." A key's winner is
stable if the winner's Lamport timestamp is STRICTLY greater than all other
operations on that key (i.e., no tie-breaking was needed). If the winning
operation's Lamport timestamp equals that of any other operation on the same
key, the winner is UNSTABLE. The stability_score is the fraction of keys
whose winner is stable (6 decimal places).

### causality_ratio

The fraction of all ORDERED pairs (not unordered) of same-key operations
(A, B) where A was issued before B in total order, such that A
happens-before B. Express as a value between 0 and 1, rounded to 6 decimal
places.

Denominator: for each key with N operations, there are N*(N-1)/2 ordered
pairs (where A appears before B in total order). Sum across all keys.

Numerator: among those pairs, count those where A happens-before B.

### vector_clock_magnitude

For each operation in the merged log, compute the **magnitude** of its
vector clock as the sum of all values in the clock. Report:
- `min_magnitude`: minimum across all operations
- `max_magnitude`: maximum across all operations
- `mean_magnitude`: mean across all operations (6 decimal places)

## Output Schema

```json
{
  "anomalies": [...],
  "convergence": {
    "causality_ratio": <float, 6 decimals>,
    "causal_depth": {
      "avg_causal_depth": <float, 6 decimals>,
      "max_causal_depth": <int>,
      "per_key": {<key: int, sorted by key>}
    },
    "stability_score": <float, 6 decimals>,
    "vector_clock_magnitude": {
      "max_magnitude": <int>,
      "mean_magnitude": <float, 6 decimals>,
      "min_magnitude": <int>
    }
  },
  "key_states": [...],
  "merged_log": [...],
  "metadata": {...},
  "summary": {...}
}
```

### Sorting Rules

- `merged_log`: sorted by Lamport timestamp asc, then replica_id asc, then op_id asc
- `key_states`: sorted by key ascending (lexicographic)
- `anomalies`: sorted by type ascending, then by first op_id in the op_ids list ascending
- `replica_ids` in metadata: sorted ascending
- All vector_clock objects: keys sorted ascending
- All JSON keys at every level: sorted ascending
- 2-space indentation, trailing newline
- Floating-point values in convergence section: exactly 6 decimal places (e.g., 0.500000 not 0.5)
