# Repair Cost Model

## Parallel Repair

The system uses a **parallel repair model** where independent subtrees can be repaired concurrently. This means the cost of repairing a parent node's subtree is determined by its own weight plus the **most expensive** child's subtree cost (since all children repair in parallel, only the slowest matters).

## Formula

```
repair_cost(node) =
  if node is a leaf:
    weight(node)
  else:
    weight(node) + MAX(repair_cost(child) for each child of node)
```

## Key Distinction: Parallel vs Sequential

- **Parallel** (this system): `weight + MAX(children)` -- children repaired concurrently
- **Sequential** (NOT used): `weight + SUM(children)` -- children repaired one by one

The `config.json` field `repair_model: "parallel"` confirms the parallel model.

## Weights

Node weights are defined in `data/weights.json`. Each weight represents the time cost to validate and repair that specific node (excluding its subtree).

## Example

Consider a node X (weight=5) with children A (repair_cost=3) and B (repair_cost=7):
- Parallel: repair_cost(X) = 5 + max(3, 7) = 12
- Sequential: repair_cost(X) = 5 + (3 + 7) = 15

The correct answer for this system is **12**.

## Computation Order

Repair costs must be computed bottom-up (leaves first), using reverse topological order. This ensures all children's costs are known before computing a parent's cost.
