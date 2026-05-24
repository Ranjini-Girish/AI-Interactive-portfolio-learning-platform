# Depth Computation Rules

## Definition

The **depth** of a node is the number of edges on the **longest path** from any root to that node.

- Root nodes have depth 0.
- For any other node, depth = max(depth(parent) + 1) across all parents.

## Why Longest Path?

In a Merkle DAG used for content addressing, depth represents the maximum dependency chain length. Using shortest path would understate the true verification depth required.

## Correct Algorithm

For a DAG, the longest-path depth can be computed via topological relaxation:

```
1. Compute topological order of all nodes (roots first)
2. Initialize depth[root] = 0 for all roots
3. For each node u in topological order:
     For each child v of u:
       depth[v] = max(depth[v], depth[u] + 1)
```

This runs in O(V + E) time and correctly handles nodes reachable via multiple paths of different lengths.

## Common Pitfall: BFS Level Traversal

A naive BFS from roots assigns each node the depth at which it is *first discovered*. In a DAG with shortcut edges, this gives the **shortest** path depth, not the longest. BFS-based depth computation is incorrect for this task.

Example: If node X is reachable via:
- Root -> X (depth 1, shortcut edge)
- Root -> A -> B -> X (depth 3, normal path)

BFS discovers X at depth 1 (first encountered). The correct longest-path depth is 3.

## Expected Values (for verification)

Given the input graph with shortcut edges `n01->n13` and `n02->n16`:
- n13 has longest-path depth 3 (via n01->n03->n07->n13), NOT depth 1 (via shortcut n01->n13)
- n16 has longest-path depth 3 (via n01->n04->n09->n16 or similar), NOT depth 1 (via shortcut n02->n16)
- n20 has longest-path depth 4 (via n01->n03->n07->n13->n20)
