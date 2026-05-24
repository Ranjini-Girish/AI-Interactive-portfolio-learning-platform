# Hash Computation Specification

## Algorithm

Each node's hash is computed as a truncated SHA-256 digest of a canonical input string.

## Parameters (from `data/hash_params.json`)

| Parameter | Value | Description |
|-----------|-------|-------------|
| salt_prefix | `merkle-v1` | Prepended to every hash input |
| separator | `\|` | Delimits fields in the hash input |
| children_join | `+` | Joins children's hashes together |
| leaf_marker | `leaf` | Appended for leaf nodes |
| children_sort_by | `hash_value` | How children's hashes are ordered before joining |

## Hash Input Construction

### Leaf Nodes (no children)

```
hash_input = "{salt_prefix}{sep}{node_id}{sep}{content}{sep}{leaf_marker}"
```

Example for node `n15` with content `cert-validator`:
```
hash_input = "merkle-v1|n15|cert-validator|leaf"
```

### Internal Nodes (has children)

```
hash_input = "{salt_prefix}{sep}{node_id}{sep}{content}{sep}{sorted_children_hashes}"
```

Where `sorted_children_hashes` is constructed by:
1. Collecting the computed hash of each child node
2. **Sorting these hash strings lexicographically by the hash value itself** (NOT by the child's node ID)
3. Joining them with the `children_join` separator (`+`)

Example: If node `n07` has children `n13` (hash `abc123...`) and `n14` (hash `99ff00...`):
- Sort by hash value: `99ff00...` < `abc123...`
- Joined: `99ff00...+abc123...`
- Full input: `merkle-v1|n07|user-store|99ff00...+abc123...`

### Critical Detail

The `children_sort_by: "hash_value"` parameter is authoritative. Children must be sorted by their **computed hash string** (lexicographic comparison of the hex-encoded hash), not by their node IDs. Node IDs happen to be in `n01`-`n20` format which is separately ordered; sorting by ID will produce incorrect hashes for nodes whose children have hashes that don't sort in the same order as their IDs.

## Truncation

The SHA-256 digest (32 bytes) is truncated to the first `hash_truncate_bytes` bytes (16 bytes = 32 hex characters) as specified in `config.json`.

## Computation Order

Hashes must be computed bottom-up: all children's hashes are computed before their parents. A topological sort (leaves first) ensures correct ordering.
