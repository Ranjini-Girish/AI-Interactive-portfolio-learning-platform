# Output Format Specification

The output file is `/app/output/dep_audit.json` — a JSON object with 2-space indentation, sorted keys at every nesting level, and a trailing newline.

## Top-Level Keys

- `build_order` — array of package names in topological build order
- `cycles` — array of cycle arrays (each cycle is an array of package names forming a loop, starting and ending with the same name); empty array if no cycles
- `metadata` — object with resolution metadata
- `resolved_packages` — array of resolved package objects, sorted by package name
- `root_modules` — array of root module objects, sorted by module name
- `schema_version` — integer, always 1
- `source_checksum` — SHA-256 hex digest of the registry.json file content (after normalizing line endings to `\n` and stripping a single trailing newline if present)
- `summary` — aggregate statistics object
- `vulnerabilities` — array of vulnerability finding objects

## Metadata Object

- `prerelease_policy` — string from policy config
- `resolution_strategy` — string from policy config
- `total_registry_packages` — integer count of all packages in the registry
- `total_registry_versions` — integer count of all versions across all packages

## Root Module Object

- `dependencies` — sorted array of direct dependency package names (depth-1 packages required by this root)
- `module_name` — string
- `version` — string

## Resolved Package Object

- `constraint_path` — array of package names showing the path from root that determined this version
- `depth` — integer
- `fan_in` — integer
- `fan_out` — integer
- `instability` — float, 6 decimal places
- `max_vuln_score` — float (maximum vulnerability score propagated to this package), 6 decimal places; 0.0 if no vulnerabilities
- `package` — string
- `required_by` — sorted array of package names that directly depend on this package
- `version` — string

## Vulnerability Finding Object

- `advisory_id` — string
- `affected_package` — string (the directly vulnerable package)
- `affected_version` — string (the resolved version)
- `cvss` — float
- `propagated_to` — sorted array of objects, each with `package` (string) and `score` (float, 6 decimal places), representing packages that inherit this vulnerability transitively
- `severity` — string
- `title` — string

## Summary Object

- `avg_instability` — float, 6 decimal places
- `critical_vulns` — integer count of critical severity vulnerabilities affecting resolved packages
- `max_depth` — integer
- `total_direct` — integer
- `total_packages` — integer
- `total_transitive` — integer
- `vulnerability_score` — float, geometric mean of max_vuln_score values, 6 decimal places

## Source Checksum

Compute SHA-256 of `/app/data/registry.json` content after normalizing line endings to `\n` and stripping a single trailing newline if present. Output as lowercase hex.

## Sorting Rules

- All JSON object keys sorted alphabetically at every nesting level
- `resolved_packages` sorted by `package` name
- `required_by` arrays sorted alphabetically
- `propagated_to` arrays sorted by `package` name
- `build_order` in topological order (not alphabetical)
- `vulnerabilities` sorted by `advisory_id`
