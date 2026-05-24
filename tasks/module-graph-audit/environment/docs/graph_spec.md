# Dependency Graph Specification

## Edge Types

Each dependency between two modules creates an edge in the dependency graph.

- **static**: Created by any `import ... from '...'` or `export ... from '...'` statement.
- **dynamic**: Created by `import('...')` expressions.

A single source-target pair should appear at most once per type. If module A has both a static import and a re-export from module B, there is still only one static edge from A to B.

## Edge List

The `dependency_edges` array contains objects with:
- `source`: module_id of the importing module
- `target`: module_id of the imported module
- `type`: "static" or "dynamic"

Sort edges by (source, target, type) lexicographically.

## Coupling Metrics

For each module, compute:

- **afferent_coupling** (Ca): Number of modules that have a static dependency ON this module (i.e., this module appears as `target` in static edges). Do NOT count dynamic edges for coupling.
- **efferent_coupling** (Ce): Number of modules that this module has a static dependency on (i.e., this module appears as `source` in static edges). Do NOT count dynamic edges for coupling.
- **instability** (I): Ce / (Ca + Ce). If Ca + Ce = 0, instability is null.

Round instability to the precision specified in `output_precision` (6 decimal places).

## Circular Dependency Detection

Use Tarjan's algorithm to find Strongly Connected Components (SCCs) in the static dependency graph. Only report SCCs with 2 or more members.

For each SCC:
- `cycle_id`: Sequential integer starting at 1, ordered by the lexicographically smallest member
- `modules`: Sorted list of module_ids in the SCC
- `representative`: The lexicographically smallest module_id

## Topological Layers

Assign each module a layer on the condensation DAG:
- Modules with no outgoing static dependencies (and not in an SCC with outgoing deps) are layer 0.
- Otherwise, layer = 1 + max(layer of all static dependency targets).
- All modules in the same SCC share the same layer (computed on the condensation graph where each SCC is collapsed to a single node).
