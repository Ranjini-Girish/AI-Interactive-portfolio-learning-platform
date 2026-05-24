# Architecture

## Module Structure

```
src/
├── main.js       — Entry point: loads data, runs engine, writes output
├── engine.js     — Engine class: orchestrates cells, updates, recalculation
├── graph.js      — DependencyGraph: edge tracking, topological sort, cycle detection
└── formulas.js   — Formula parsing (tokenizer + recursive descent) and evaluation
```

## Data Flow

1. `main.js` loads config, initial state, and update sequence from `/app/data/`
2. Creates an `Engine` instance with the config
3. Adds all initial cells via `engine.addCell()`
4. Processes each update via `engine.updateCell()` or `engine.batchUpdate()`
5. Collects final state, audit trail, cycle report
6. Writes `/app/output/results.json`

## Engine Internals

The engine maintains:
- `cells` Map: cell ID → { id, formula, value, isFormula }
- `graph` DependencyGraph: tracks which cells depend on which
- `audit` Array: chronological log of all recalculation events
- `recalcCounts` Map: cell ID → number of times recalculated
- `errorCells` Map: cell ID → Error for cells in error state

## Graph Implementation

The DependencyGraph uses two adjacency maps:
- `edges`: cell → Set of cells it DEPENDS ON (its inputs)
- `reverseEdges`: cell → Set of cells that DEPEND ON IT (its outputs)

Topological sort uses Kahn's algorithm (iterative in-degree reduction).
Cycle detection uses iterative DFS with a "visiting" state marker.

## Formula Evaluation

The formula evaluator is a two-phase system:
1. `parse(formula)` → AST (recursive descent parser)
2. `evaluate(ast, getCellValue, config)` → numeric value

The getCellValue callback resolves cell references during evaluation.
