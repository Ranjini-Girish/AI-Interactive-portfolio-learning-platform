# Resolution Algorithm

## Overview

The resolver takes a workspace manifest and a crate registry, then determines
the exact version of every crate needed to satisfy all constraints.

## Constraint Semantics

### Caret (`^`)

Allows changes that do not modify the leftmost non-zero digit:

| Constraint | Equivalent Range |
|---|---|
| `^1.2.3` | `>=1.2.3, <2.0.0` |
| `^0.2.3` | `>=0.2.3, <0.3.0` |
| `^0.0.3` | `>=0.0.3, <0.0.4` |
| `^1.2`   | `>=1.2.0, <2.0.0` |
| `^0.0`   | `>=0.0.0, <0.1.0` |

### Tilde (`~`)

Allows patch-level changes only (pins major.minor):

| Constraint | Equivalent Range |
|---|---|
| `~1.2.3` | `>=1.2.3, <1.3.0` |
| `~0.1.5` | `>=0.1.5, <0.2.0` |
| `~2.0`   | `>=2.0.0, <2.1.0` |

### Exact

No prefix means exact match: `1.2.3` matches only `1.2.3`.

### Comparison operators

`>=`, `>`, `<`, `<=` followed by a version. Multiple constraints
separated by `, ` (comma-space) must ALL be satisfied.

## Resolution Process

1. Initialize the constraint map from the root manifest's dependencies.
2. For each crate in the constraint map, find the HIGHEST version in the
   registry that satisfies ALL accumulated constraints for that crate.
3. For each newly resolved crate version, inspect its dependencies:
   - Required (non-optional) deps: add their version constraints to the map.
   - Optional deps: add ONLY if the corresponding feature is enabled.
4. Merge features: if `default_features` is true for a dependency, enable
   the `default` feature. Then recursively expand all enabled features
   (features can reference other features or `dep:X` to activate optional deps).
5. If new constraints were added or any resolution changed, repeat from step 2.
6. Continue until the constraint map and resolved versions are stable (fixed-point).

## Conflict Detection

If no version of a crate satisfies all constraints simultaneously, record a
conflict entry with the crate name and the unsatisfiable constraint set.

## Feature Expansion

Feature values can be:
- A plain feature name (e.g., `"std"`) — activates that feature on the same crate.
- `"dep:X"` — activates the optional dependency named `X` (makes it required).

Expansion is recursive: enabling feature A may enable features B and C,
which may enable more deps. Continue until no new features are activated.

**Important:** `dep:X` entries are activation directives only. They must NOT
appear in the output `features` list for any crate. Only named features
(those that are keys in the feature map) are included in the output.

## Depth Calculation

Depth = length of the shortest dependency path from the root manifest.
Direct dependencies have depth 1. A crate reachable through 2 intermediate
crates has depth 3. Use BFS from the root to compute shortest paths.

## Dependents

For each resolved crate, `dependents` lists all crates (and "my-app" for
direct deps) that directly depend on it. Sorted alphabetically.
