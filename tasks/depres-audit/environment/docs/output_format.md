# Output Format Specification

Write to `/app/output/dep_health_report.json` with 2-space indent and trailing newline.

## Top-Level Keys (sorted)

1. `build_order`: Array of crate names in topological order (see resolution_spec.md).
2. `config`: Copy of workspace configuration.
3. `conflicts`: Array of conflict objects, sorted by crate_name.
4. `crate_metrics`: Object keyed by crate name (sorted), each with:
   - `version`: resolved version string
   - `license`: license of the resolved version
   - `deprecated`: boolean
   - `freshness`: float
   - `staleness`: float
   - `ca`: integer (afferent coupling)
   - `ce`: integer (efferent coupling)
   - `instability`: float
5. `health_ranking`: Array of member names in health-ranked order.
6. `members`: Object keyed by member name (sorted), each with:
   - `direct_deps`: sorted array of direct dep names
   - `resolved_versions`: object mapping crate→version (sorted)
   - `dep_tree_depth`: integer
   - `weighted_staleness`: float
   - `license_audit`: object with `license_clean` and `violations`
   - `health_score`: float
   - `health_grade`: string
   - `deprecated_deps`: sorted array of deprecated crate names
7. `summary`: object with:
   - `total_workspace_members`: integer
   - `total_unified_crates`: integer
   - `total_conflicts`: integer
   - `avg_health_score`: float (arithmetic mean of all member health_scores, rounded)
   - `healthiest_member`: name of the member with the best (highest) health_score (ties: first in health_ranking)
   - `max_dep_tree_depth`: integer
   - `total_license_violations`: integer (sum of violations across all members)
   - `total_deprecated_deps`: integer (count of unique deprecated resolved crates)
8. `unified_versions`: Object mapping crate→version (sorted), excluding conflicting crates.

## Conflict Object

Each has: `crate_name`, `requirements` array. Each requirement has: `range`, `required_by` (chain array), `best_match`.

Sort conflicts by crate_name. Sort requirements within by (required_by[0], range).
