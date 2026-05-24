# Merkle DAG Validator -- Algorithm Specification

## Overview

The validator performs four main phases:

1. **Hash Computation** -- Computes cryptographic hashes for every node using the scheme defined in `hash_spec.md`.
2. **Validation** -- Compares each node's declared hash against the computed hash to detect corruption. Every node with a mismatch is flagged as corrupted regardless of its position in the DAG (leaves, single-child nodes, and multi-child nodes are all validated).
3. **Metrics Computation** -- Computes per-node metrics: depth, repair cost, reachability, and subtree size.
4. **Report Generation** -- Produces a structured JSON report with metadata, per-node data, findings sorted by severity/depth, and a summary.

## Phase 1: Hash Computation

Hashes are computed bottom-up (leaves first, roots last). The hash of each node depends on its children's hashes. See `hash_spec.md` for the exact formula.

## Phase 2: Validation

For each node in the DAG:
- Compute its hash using the canonical algorithm
- Compare against `declared_hash` from the input data
- If they differ, emit a finding with type `hash_mismatch`

**Important**: ALL nodes are validated. There is no exemption based on child count, leaf status, or position in the graph. A leaf node with a wrong declared_hash is just as corrupted as an internal node.

## Phase 3: Metrics

### Depth
The depth of a node is the length of the **longest path** from any root to that node, measured in edges. Roots have depth 0. This requires computing longest-path distances in a DAG (not shortest-path BFS).

The correct algorithm uses topological ordering:
1. Initialize all depths to 0
2. Process nodes in topological order (roots first)
3. For each node at depth `d`, update each child: `child.depth = max(child.depth, d + 1)`

This guarantees that every node's depth reflects its longest path from any root.

### Repair Cost
Under the **parallel repair model**, repairing a subtree rooted at node N costs:
```
repair_cost(N) = weight(N) + max(repair_cost(child) for child in children(N))
```
If N is a leaf: `repair_cost(N) = weight(N)`.

The rationale: children are repaired concurrently, so the cost is dominated by the most expensive child, not the sum.

### Reachability
A node is reachable if there exists any path from a root node to it. Standard DFS/BFS from roots suffices.

### Subtree Size
The count of nodes reachable below (and including) this node via child edges.

## Phase 4: Report Generation

The report is serialized as JSON with 2-space indentation and a trailing newline. See `output_schema.md` for the exact structure.

### Findings Sort Order
Findings are sorted by:
1. `severity_rank` **descending** (most severe first)
2. `depth` **descending** (deeper nodes first within same severity)
3. `node_id` **ascending** (alphabetical tie-breaker)
