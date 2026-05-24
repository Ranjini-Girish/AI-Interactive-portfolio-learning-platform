# Validation Rules

## Hash Validation

Every node in the DAG must be validated, regardless of its structural position:

- **Leaf nodes** (no children): validated by computing `SHA256(salt|id|content|leaf_marker)` and comparing to `declared_hash`.
- **Single-child nodes** (exactly 1 child): validated identically to multi-child nodes. There is NO special exemption or "inheritance" logic for single-child nodes.
- **Multi-child nodes** (2+ children): validated by computing the hash with children's hashes sorted by hash value.

A node is **corrupted** if and only if its `declared_hash` differs from the computed hash. The comparison is exact string equality of the 32-character hex representation.

## Severity Assignment

When a hash mismatch is detected:
- Look up `finding_type` in `data/severity_map.json`
- `hash_mismatch` -> `"critical"` (severity_rank = 3)

## Nodes with "CORRECT" Declared Hash

In the input data, nodes whose `declared_hash` field contains the literal string `"CORRECT"` should have their declared_hash replaced with the correctly computed hash during loading. This simulates nodes that were stored correctly.

Nodes with any other declared_hash value (e.g., `"CORRUPTED_08"`) represent actual corruption -- their declared hash does NOT match the computed hash.

## Expected Corrupted Nodes

Given the input data, the following nodes have non-matching declared hashes:
- `n08` -- declared_hash is `"CORRUPTED_08"` (not a valid hash)
- `n11` -- declared_hash is `"CORRUPTED_11"` (not a valid hash)
- `n20` -- declared_hash is `"CORRUPTED_20"` (not a valid hash)

All three must appear in the findings array.
