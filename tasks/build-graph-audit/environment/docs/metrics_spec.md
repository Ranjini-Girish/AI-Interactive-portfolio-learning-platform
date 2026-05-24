# Metrics Specification

## Cycle Detection

Use Tarjan's algorithm to find all Strongly Connected Components (SCCs)
with two or more members. Each SCC represents a dependency cycle.

Report each cycle with:
- `cycle_id`: 1-based, assigned in the order Tarjan's algorithm completes
  SCCs (the first SCC completed gets id 1).
- `members`: the module names in the SCC, sorted alphabetically.

## Depth Computation

Module depth is the **longest path** (in edges) from any entry point to
that module in the resolved dependency graph.

### Rules

1. Entry-point modules have depth 0.
2. For non-entry modules reachable from at least one entry point,
   `depth = max(depth(predecessor) + 1)` over all predecessors that
   have a resolved edge pointing to this module.
3. **Cycle handling**: all members of the same SCC share the same depth.
   To compute it, condense each SCC into a single node in a DAG, compute
   longest-path depths on the condensed DAG, and assign that depth to
   every member of the SCC.
4. Modules not reachable from any entry point have `depth = null`.

## Coupling Metrics

- **Fan-in (Ca)**: the number of modules that have a resolved dependency
  edge pointing to this module (afferent coupling).
- **Fan-out (Ce)**: the number of modules this module has resolved
  dependency edges pointing to (efferent coupling).
- **Instability**: `I = Ce / (Ca + Ce)`. When both Ca and Ce are zero,
  instability is `null` (not 0, not NaN).

## Layer Classification

- `"entry"`: the module is listed in `project.entry_points`.
- `"leaf"`: the module has fan-out = 0 and is reachable.
- `"unreachable"`: the module is not reachable from any entry point.
- `"internal"`: all other reachable modules.

## Size Transforms

Transforms are applied multiplicatively:

```
minified_bytes = raw_size_bytes × minify_ratio
compressed_bytes = minified_bytes × compress_ratio
                 = raw_size_bytes × minify_ratio × compress_ratio
```

These are **not** additive reductions. A `minify_ratio` of 0.65 means
the minified output is 65% of the original size (not a 65% reduction).

## Used-Export Analysis

For each module, determine which of its **own exports** are actually
imported by at least one other module. A specifier counts as "used"
if any module resolves an import of that specifier to this module
through the standard import-resolution process (including re-export
chain following).

### Rules

1. **Entry-point modules**: all exports are considered "used" regardless
   of whether other modules import them. `used_export_ratio = 1.0`.
2. **Re-export attribution**: when module A imports specifier X from B,
   and B re-exports X from C, the specifier X counts as a used export
   of **C** (the terminal provider), not of B.
3. **Side-effect imports**: an import with empty specifiers (`[]`) does
   not mark any specific export as "used" on the target module.
4. **Counting**: `used_exports` is the count of distinct own-export
   specifiers that are used. `total_exports` is the length of the
   module's `exports` array. `used_export_ratio = used_exports / total_exports`.
   When `total_exports` is 0, `used_export_ratio` is `null`.
5. **Re-export specifiers are NOT own exports**: if module B re-exports
   specifier X from C, X is **not** part of B's `exports` array and
   does not affect B's `used_exports` or `total_exports`.

### Tree-Shaking Eligibility

A module is tree-shake eligible when **all** of these hold:
- `side_effects` is `false`
- The module is **not** a member of any dependency cycle

For eligible modules:
```
potential_savings_bytes = raw_size_bytes × (1 - used_export_ratio)
```

For ineligible modules: `potential_savings_bytes = 0`.

## Build Order

A valid **topological build order** lists modules such that every
dependency of a module appears before it. Since the graph may contain
cycles, condense SCCs first: members of an SCC are listed together
in alphabetical order, at the position determined by the condensed
DAG's topological sort.

Within the condensed DAG, when multiple nodes have no remaining
in-edges, process them in alphabetical order (by the SCC's
representative, which is the alphabetically first member).
