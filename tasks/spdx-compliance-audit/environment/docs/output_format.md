# Output Format

The audit report is a JSON object written to `/app/output/audit_report.json`
with 2-space indentation and a trailing newline.

## Top-Level Structure

```json
{
  "metadata": { ... },
  "projects": [ ... ],
  "summary": { ... }
}
```

## Metadata Block

| Field | Type | Description |
|---|---|---|
| `total_projects` | integer | Number of project files in `data/projects/` |
| `total_packages` | integer | Number of package definition files in `data/packages/` — this is the total catalogue size, not the sum of per-project resolved dependency counts |
| `policy_version` | string | Value of the `version` field from `config/policy.json` |

## Per-Project Fields

Each object in the `projects` array is sorted by `project_id` ascending.

| Field | Type | Description |
|---|---|---|
| `project_id` | string | Matches the `project_id` in the project file |
| `project_license` | string | The project's own declared license |
| `dependency_count` | integer | Total resolved dependencies (direct + transitive, deduplicated to shallowest occurrence) |
| `direct_dependency_count` | integer | Count of depth-0 dependencies |
| `max_depth` | integer | Deepest level in the resolved dependency tree |
| `dependencies` | array | Dependency entries — see schema below |
| `violations` | array | Violation entries — see schema below |
| `risk_score` | number | Weighted risk score, rounded to 4 decimal places (see `risk_scoring.md`) |

## Dependency Entry Schema

Each entry in a project's `dependencies` array:

| Field | Type | Description |
|---|---|---|
| `package_name` | string | Package name as declared in its package file |
| `version` | string | Package version string |
| `declared_license` | string | License field exactly as written in the package file |
| `effective_license` | string | Resolved license after SPDX expression evaluation (see `license_rules.md`). For AND expressions this is the full combined string, e.g. `"MIT AND BSD-2-Clause"`. For OR expressions this is the chosen single identifier. |
| `license_category` | string | One of `"allowed"`, `"restricted"`, `"banned"` |
| `depth` | integer | `0` for direct dependencies; increments by 1 per transitive hop |

Sorted by `(depth ASC, package_name ASC)`.

## Violation Entry Schema

Each entry in a project's `violations` array:

| Field | Type | Description |
|---|---|---|
| `package_name` | string | Package with the violation |
| `declared_license` | string | License field from the package file |
| `violation_type` | string | One of `"banned_license"`, `"restricted_license"`, `"copyleft_propagation"` |
| `severity` | integer | Severity value from the policy |
| `depth` | integer | Resolved depth of this package in the project |
| `dependency_path` | array of strings | Path from project root to this package, e.g. `["web-api", "sharp", "libvips"]` |
| `waived` | boolean | `true` if a policy waiver applies for this package in this project |
| `propagated_from` | string | *(copyleft_propagation only)* Name of the copyleft source package |
| `source_license` | string | *(copyleft_propagation only)* License of the copyleft source package |

Sorted by `(severity DESC, depth ASC, package_name ASC)`.

## Summary Fields

| Field | Type | Description |
|---|---|---|
| `total_violations` | integer | Sum of all violation entries across every project |
| `total_waived` | integer | Count of violations where `waived` is `true` across all projects |
| `projects_at_risk` | integer | Count of projects whose `risk_score` is greater than `0` |
| `highest_risk_project` | string | `project_id` of the project with the highest `risk_score` |
| `most_common_violation_license` | string | License appearing most often as the root cause of violations — counts copyleft propagation by its `source_license`; ties broken alphabetically |
