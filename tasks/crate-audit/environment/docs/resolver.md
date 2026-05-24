# Dependency Resolver Algorithm

## Overview

The resolver reads the project manifest and package registry to compute a complete set of resolved packages with their exact versions.

## Resolution Process

1. Start with the project's direct dependencies and their constraints.
2. For each dependency, find the highest version in the registry that satisfies the constraint.
3. Load that version's dependencies and add them to the resolution queue.
4. When a package is already resolved, verify that the new constraint is compatible with the resolved version.
5. Repeat until no unresolved dependencies remain.

Packages not reachable from the project's dependency graph are excluded from the resolution.

## Build Order

The build order is a topological ordering of the resolved dependency graph. Packages with no dependencies are built first, followed by packages whose dependencies have all been built.

When multiple packages are eligible for the next position (all dependencies satisfied), they are ordered alphabetically by package name.

## Vulnerability Scoring

Each package version has a base vulnerability score (0.0 means no known vulnerabilities). The propagated vulnerability score accounts for transitive risk:

The effective score for a package equals its base score plus the decay factor multiplied by the sum of the effective scores of all its direct dependencies. The decay factor (specified in config) attenuates risk from indirect dependencies.

Packages with an effective vulnerability score greater than 0.0 are considered vulnerable.

## License Compatibility

License categories define a hierarchy from most permissive to most restrictive:

    permissive < weak_copyleft < strong_copyleft

A license conflict occurs when a package depends on another package with a more restrictive license category. Only direct dependency relationships are checked for license conflicts.

## Topological Depth

The depth of a package represents its level in the dependency graph, measured as the longest path from the project root through the dependency chain to reach that package. Direct project dependencies may have a depth greater than 1 if they also appear as transitive dependencies through longer paths.

## Statistics

- **total_packages**: Count of resolved packages (excluding the project itself).
- **max_depth**: Maximum depth across all resolved packages.
- **avg_depth**: Average depth across all resolved packages, rounded to `output_precision` decimal places.
- **total_edges**: Total number of direct dependency relationships in the resolved graph.
- **max_fan_out**: Maximum number of direct dependencies any single package has.
- **max_fan_in**: Maximum number of dependents any single package has (reverse dependencies in the resolved graph, excluding the project root).
