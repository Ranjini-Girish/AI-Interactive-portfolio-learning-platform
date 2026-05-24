# Coupling Metrics Specification

## Scope

Metrics are computed over the UNIFIED dependency graph (non-conflicting crates only). Workspace members are excluded from the graph — only resolved registry crates participate.

## Afferent Coupling (Ca)

Ca for a crate = the number of OTHER crates in the unified graph that depend on it. Workspace members' direct dependencies do NOT count — only crate-to-crate edges within the unified graph count.

## Efferent Coupling (Ce)

Ce for a crate = the number of OTHER crates in the unified graph that it depends on.

## Instability (I)

I = Ce / (Ca + Ce)

If Ca + Ce = 0, then I = 0.0.

Round to output_precision decimal places.

## Version Freshness

For each resolved crate, compute freshness within the FULL version list (all versions in the registry, regardless of compatibility):

freshness = index / (total - 1)

where `index` is the 0-based position of the resolved version in the version list sorted ascending by semver, and `total` is the total number of versions for that crate.

If total = 1, freshness = 1.0.

Round to output_precision decimal places.

## Staleness

staleness = 1.0 - freshness

## Weighted Staleness (per workspace member)

For each workspace member, compute weighted mean staleness across its DIRECT dependencies only (not transitive):

weighted_staleness = Σ(staleness_i × weight_i) / Σ(weight_i)

where weight_i = Ca_i + 1 (afferent coupling of the dependency plus 1, to avoid zero weights). If the dependency is a conflicting crate (not in unified), use Ca = 0 for its weight.

Round to output_precision decimal places.
