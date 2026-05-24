# Output Specification

The program must produce a single JSON file at `/app/output/gem_audit.json` with 2-space indentation, sorted keys at all nesting levels, and a trailing newline character.

## Top-Level Structure

The output object contains these keys:

- `findings` — array of all findings across all projects, sorted as described in the resolution algorithm
- `project_audits` — array of per-project audit results, sorted by project_id
- `schema_version` — integer, always 1
- `source_hashes` — object mapping relative file paths to their SHA-256 hex digests
- `summary` — object with aggregate statistics

## Summary Object

Contains: `aggregate_risk_score` (float, geometric mean of all finding risk scores, 6 decimals), `findings_by_severity` (object mapping each severity to its count — all five levels must be present even if zero), `findings_by_type` (object mapping finding type strings to counts, sorted alphabetically), `total_conflicts` (integer), `total_findings` (integer), `total_gems_resolved` (integer, sum across all projects), `total_projects` (integer).

## Project Audit Object

Contains: `findings` (array of findings for this project), `metrics` (object with avg_depth, direct_count, max_depth, total_resolved, transitive_count, vulnerability_count), `project_id` (string), `project_license` (string), `resolved_dependencies` (array), `version_conflicts` (array).

## Resolved Dependency Object

Contains: `constraint_sources` (array of strings — gem names or "direct" that imposed constraints on this gem), `depth` (integer), `gem_name` (string), `license` (string), `path` (array of strings from project_id to this gem), `version` (string).

## Finding Object

Contains: `evidence` (object with finding-specific details), `finding_type` (string), `gem_name` (string), `project_id` (string), `risk_score` (float, 6 decimals), `severity` (string), `version` (string or null for conflict findings).

All float values must be rounded to exactly 6 decimal places.
