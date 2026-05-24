# Dependency Metrics Specification

## Package-Level Metrics

### Fan-In (Afferent Coupling)

Number of other resolved packages that **directly depend on** this package.

### Fan-Out (Efferent Coupling)

Number of other resolved packages that this package **directly depends on** (using the resolved version's dependency list, but only counting packages that are actually in the resolved set).

### Instability

```
I = fan_out / (fan_in + fan_out)
```

When `fan_in + fan_out = 0`, instability is `0.0`.

Round to 6 decimal places.

### Depth

Shortest path distance from any root module. Root modules have depth 0. A direct dependency of a root has depth 1, and so on.

## Vulnerability Propagation

For each advisory matching a resolved package version:

1. Compute `direct_score = severity_weight` (from policy config).
2. Compute `propagated_score` for each package that transitively depends on the vulnerable package:
   ```
   propagated_score = severity_weight × depth_decay_base ^ hop_distance
   ```
   where `hop_distance` is the number of edges in the shortest path from the dependent package to the vulnerable package in the resolved dependency graph.
3. A package's `max_vuln_score` is the maximum of all propagated scores reaching it (from any vulnerable dependency).

## Build Order

Compute a topological sort of the resolved dependency graph. Packages with no dependencies come first.

Tie-breaking: when multiple packages have zero in-degree simultaneously, sort them lexicographically by package name.

### Cycle Handling

If the resolved graph contains a cycle, break it by removing the edge pointing to the lexicographically smallest package name in the cycle, then re-run the topological sort. Record all detected cycles as arrays of package names forming the cycle (starting and ending with the same package).

## Aggregate Metrics

### Summary Statistics

- `total_packages`: count of resolved packages (excluding root modules)
- `total_direct`: count of packages at depth 1
- `total_transitive`: count of packages at depth > 1
- `max_depth`: maximum depth in the resolved graph
- `avg_instability`: arithmetic mean of all package instability values, 6 decimal places
- `vulnerability_score`: geometric mean of all `max_vuln_score` values across packages that have at least one vulnerability propagated to them. If no vulnerabilities, 0.0. Round to 6 decimal places.

### Geometric Mean

```
geometric_mean = exp(mean(ln(v₁), ln(v₂), ..., ln(vₙ)))
```

Only positive values are included. If the set is empty, result is 0.0.
