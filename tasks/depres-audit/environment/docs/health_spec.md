# Health Scoring Specification

## Per-Member Health Score

For each workspace member, compute:

health_score = (1.0 - weighted_staleness) × conflict_factor × license_factor

Where:
- `weighted_staleness` is from metrics_spec.md
- `conflict_factor` = 1.0 - (num_conflicting_direct_deps / total_direct_deps)
  - `num_conflicting_direct_deps` = count of the member's DIRECT dependencies that are in the global conflicts list
  - `total_direct_deps` = total count of the member's direct dependencies
- `license_factor` = 1.0 if license_clean is true, 0.5 if false

The three factors are MULTIPLIED, not added or averaged.

Round to output_precision decimal places.

## Health Grade

Based on health_score:
- "A" if health_score >= 0.8
- "B" if health_score >= 0.6
- "C" if health_score >= 0.4
- "D" if health_score >= 0.2
- "F" if health_score < 0.2

Note: thresholds use >= (greater-than-or-equal), not > (strict greater-than).

## Deprecation Warnings

For each workspace member, list any resolved dependency whose version is marked `deprecated: true` in the registry. Sort by crate name.

## Health Ranking

Sort workspace members by:
1. health_grade — ASCENDING (A < B < C < D < F)
2. health_score — DESCENDING (higher is better within same grade)
3. member name — ASCENDING (lexicographic)
