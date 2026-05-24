# Dependency Resolution Specification

## Per-Member Resolution

For each workspace member, resolve direct and transitive dependencies. All workspace members share a unified resolution when possible.

## Unified Resolution

Collect all version requirements for each crate across all members and transitive deps. Compute the intersection. Select the highest version in the intersection. If empty, record a conflict.

## Conflict Handling

When a conflict exists, the conflicting crate does NOT appear in `unified_versions`. Each workspace member that needs the crate resolves it independently using only its own path's constraints. The per-member `resolved_versions` may contain different versions for a conflicting crate.

## Dependency Depth

`dep_tree_depth` for a member is the longest chain of transitive dependencies. Direct dep with no further deps = depth 1. No deps = depth 0.

## Build Order

Topological ordering of all non-conflicting resolved crates. When multiple crates have zero in-degree, use the 3-level tie-breaking key:
1. Number of dependents (crates depending on this one) — DESCENDING
2. Total coupling score (Ca + Ce, see metrics_spec.md) — DESCENDING
3. Crate name — ASCENDING (lexicographic)

This ensures heavily-depended-upon crates are built first.
