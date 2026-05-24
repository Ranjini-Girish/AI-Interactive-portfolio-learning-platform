# Reactive Dataflow Engine — Specification

## Overview

The engine manages a set of named cells. Each cell holds either a plain value or a formula that references other cells. When a cell's value changes, all cells that depend on it (directly or transitively) are recalculated automatically.

## Cell Definitions

A cell is defined by either:
- `{ "value": <number> }` — a plain value cell (no dependencies)
- `{ "formula": "<expression>" }` — a formula cell (depends on referenced cells)

Cell IDs follow the pattern `[A-Z][A-Z0-9]*[0-9]+` (e.g., A1, B2, G4, M12).

## Formula Language

Expressions support:
- Arithmetic: `+`, `-`, `*`, `/`
- Comparisons: `>`, `<`, `>=`, `<=`, `==`, `!=` (return 1 for true, 0 for false)
- Cell references: any valid cell ID
- Parentheses for grouping

### Built-in Functions

- `SUM(a, b, ...)` — sum of all arguments
- `AVG(a, b, ...)` — arithmetic mean of all arguments
- `MIN(a, b, ...)` — minimum value
- `MAX(a, b, ...)` — maximum value
- `IF(condition, then_value, else_value)` — conditional evaluation
- `ABS(x)` — absolute value
- `ROUND(x, places)` — round to N decimal places
- `COUNT(a, b, ...)` — count of arguments
- `COUNTIF(a, b, ..., threshold)` — count of args (excluding last) that are > threshold

## Evaluation Semantics

### Precision

All intermediate calculations retain full JavaScript double-precision internally. The configured output precision (default: 6 decimal places) applies ONLY when writing the final JSON output. Division, multiplication, and all other arithmetic operations produce full-precision IEEE 754 doubles that are passed unchanged to dependent cells.

### IF Function Short-Circuit

The IF function uses short-circuit evaluation: only the branch selected by the condition is evaluated. If the condition is truthy (non-zero), only the then-branch is evaluated. If falsy (zero), only the else-branch is evaluated. An error in the non-selected branch does NOT propagate.

### Error Propagation

When a cell's formula references a cell in error state (e.g., part of a cycle), evaluating that reference throws an error. The referencing cell also enters error state, with value `null` in the output.

## Dependency Tracking

When a cell's formula changes, the engine must:
1. Parse the new formula to extract cell references
2. Update the dependency graph: remove ALL old edges for that cell, add new edges
3. Recalculate the cell with its new formula
4. Recalculate all transitive dependents of the changed cell

When a value cell changes, the engine recalculates all transitive dependents.

When a cell transitions between types (formula ↔ value), the dependency graph must reflect the new definition. Converting a formula cell to a plain value removes all of that cell's outgoing dependency edges. Converting a value cell to a formula establishes new edges based on the formula's cell references. These rules apply identically in single-cell updates and in batch updates.

## Recalculation Order

When multiple cells need recalculation after a change:
1. Collect all transitively affected cells
2. Topologically sort them by their dependency relationships
3. When multiple cells are at the same topological depth (no dependency between them), process them in **alphabetical order by cell ID** (ASCII sort, uppercase letters before digits in standard ordering)
4. Evaluate each cell exactly once in this order

## Batch Updates

Batch updates change multiple cells atomically:
1. Apply ALL value/formula changes first (without triggering recalculation)
2. Collect the union of all transitively affected cells
3. Topologically sort the affected set (with alphabetical tie-breaking)
4. Evaluate each affected cell exactly once in order

## Cycle Detection

The engine detects dependency cycles using depth-first search from each unvisited node. A cycle exists when DFS encounters a node currently on the recursion stack (a back-edge).

Diamond-shaped dependency graphs (A depends on B and C, both depend on D) are NOT cycles and must NOT be reported as cycles.

### Cycle Reporting

Cycles are reported as arrays of cell IDs forming the cycle path, with the first node repeated at the end (e.g., `["K1", "K3", "K2", "K1"]` for K1→K3→K2→K1).

Cells in a cycle have their value set to `null` and appear in the errors map.

## Output Format

The engine produces `/app/output/results.json` with the structure:

```
{
  "initial_snapshot": { "<cellId>": <value>, ... },
  "updates": [
    {
      "index": <int>,
      "type": "value"|"formula"|"batch",
      "cell": "<cellId>"|null,
      "recalculated_cells": ["<cellId>", ...]
    }, ...
  ],
  "final_values": { "<cellId>": <value|null>, ... },
  "cycles_detected": [ ["K1", "K3", "K2", "K1"], ... ],
  "recalc_counts": { "<cellId>": <int>, ... },
  "errors": { "<cellId>": {"message": "...", "type": "..."}, ... },
  "recalculation_order": ["<cellId>", ...]
}
```

All numeric values in `initial_snapshot` and `final_values` are rounded to the configured precision (6 decimal places). The `recalculation_order` lists every cell recalculation event in chronological order (a cell may appear multiple times if recalculated multiple times across different updates).
