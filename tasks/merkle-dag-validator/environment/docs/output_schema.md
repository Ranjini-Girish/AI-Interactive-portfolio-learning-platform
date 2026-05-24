# Output Schema -- validation_report.json

The output file is written to `/app/output/validation_report.json` with 2-space JSON indentation and a trailing newline.

## Top-Level Structure

```json
{
  "metadata": { ... },
  "nodes": [ ... ],
  "findings": [ ... ],
  "summary": { ... }
}
```

Top-level keys must appear in this exact order: `metadata`, `nodes`, `findings`, `summary`.

## metadata

| Field | Type | Description |
|-------|------|-------------|
| total_nodes | integer | Total number of nodes in the DAG |
| total_edges | integer | Total number of directed edges |
| root_count | integer | Nodes with no parents |
| leaf_count | integer | Nodes with no children |
| max_depth | integer | Maximum depth across all nodes (longest-path depth) |

## nodes

Array of node entries sorted by `id` ascending. Each entry:

| Field | Type | Description |
|-------|------|-------------|
| id | string | Node identifier |
| depth | integer | Longest-path depth from any root (0 for roots) |
| repair_cost | integer | Parallel repair cost for the subtree rooted here |
| subtree_size | integer | Count of nodes reachable below (inclusive) |
| is_leaf | boolean | True if node has no children |
| is_root | boolean | True if node has no parents |
| reachable | boolean | True if reachable from any root |
| computed_hash | string | The correctly computed hash (32 hex chars) |

## findings

Array of corruption findings sorted by:
1. `severity_rank` descending (3=critical first, 2=high, 1=low)
2. `depth` descending (deeper nodes first within same severity)
3. `node_id` ascending (alphabetical tie-break)

Each finding entry:

| Field | Type | Description |
|-------|------|-------------|
| node_id | string | Affected node |
| finding_type | string | Always `"hash_mismatch"` for corrupted nodes |
| severity | string | `"critical"`, `"high"`, or `"low"` |
| severity_rank | integer | Numeric severity (3, 2, or 1) |
| depth | integer | Node's longest-path depth |
| declared_hash | string | Hash value stored in the input data |
| computed_hash | string | Hash value computed by the validator |
| repair_cost | integer | Cost to repair this node's subtree |

## summary

| Field | Type | Description |
|-------|------|-------------|
| corrupted_count | integer | Number of nodes with hash mismatches |
| integrity_ratio | float | Fraction of nodes reachable from roots |
| total_repair_cost | integer | Sum of repair_cost across all corrupted nodes |
| max_repair_cost | integer | Maximum repair_cost among corrupted nodes |
| avg_depth | float | Average depth across all nodes |
| deep_node_count | integer | Nodes with depth > max_depth threshold (from thresholds.json) |
