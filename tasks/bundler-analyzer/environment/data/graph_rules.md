# Module Graph Construction & Circular Import Detection

## Graph construction

Build a directed graph where each internal module is a node and each static import creates a directed edge from the importing module to the imported module. Dynamic imports are **not** edges in this graph — they only define chunk boundaries. External packages are excluded from the graph entirely.

## Circular import detection

Use depth-first search from every unvisited node to find **all** simple cycles in the import graph. A cycle is a path `A → B → ... → A` where the last node equals the first.

Report each unique cycle exactly once as an array of module IDs starting and ending with the same module. The starting module of each cycle must be the **alphabetically smallest** module ID in that cycle. If two cycles share the same starting module, sort them by the second element, then third, etc.

The `has_circular_imports` flag is `true` if at least one cycle exists.

## External packages

Collect all distinct external package names (from imports with `"external": true`) into a sorted array.
