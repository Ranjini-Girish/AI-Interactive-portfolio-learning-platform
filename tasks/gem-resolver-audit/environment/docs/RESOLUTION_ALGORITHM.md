# Resolution Algorithm

## Overview

For each project, resolve its dependency tree by selecting the highest compatible version for every gem, then compute metrics and detect policy violations.

## Step 1: Scope Filtering

Only dependencies whose `group` is listed in `policy.scope_filter` are resolved. Typically only `runtime` dependencies are in scope. Development and test dependencies are excluded from the resolved tree entirely.

## Step 2: Dependency Resolution (BFS)

Starting from the project's direct runtime dependencies, perform breadth-first resolution:

1. For each dependency, collect all active constraints on that gem (from the project and from already-resolved gems that depend on it).
2. Select the highest stable version from the registry that satisfies all constraints. Pre-release versions are excluded unless the constraint explicitly references a pre-release.
3. If no version satisfies all constraints, record a version conflict.
4. Add the resolved gem's own runtime dependencies to the queue.
5. If a gem has already been resolved, skip it (first-resolved wins; BFS ensures nearest-wins for depth).
6. Stop when the queue is empty or depth exceeds `max_dependency_depth` from the policy.

Process direct dependencies in the order they appear in the project's dependency list.

## Step 3: Metrics Computation

For each project audit, compute:

- `total_resolved`: number of distinct gems resolved
- `max_depth`: maximum depth in the dependency tree (direct deps are depth 1)
- `direct_count`: number of direct runtime dependencies
- `transitive_count`: total_resolved minus direct_count
- `avg_depth`: the **harmonic mean** of all resolved gems' depths, rounded to 6 decimal places. The harmonic mean of depths d₁, d₂, …, dₙ is: `n / (1/d₁ + 1/d₂ + … + 1/dₙ)`. If n is 0, avg_depth is 0.0.
- `vulnerability_count`: number of resolved gems affected by known advisories

## Step 4: Advisory Matching

For each resolved gem, check if its version falls within any advisory's `affected_versions` range. An advisory's `affected_versions` is an array of version constraints (same syntax as dependency constraints). If the resolved version satisfies ALL constraints in that array, the gem is affected.

## Step 5: License Findings

For each resolved runtime gem, check:

1. **Banned license**: if the gem's license is in `policy.banned_licenses`, emit a `banned_license` finding.
2. **License incompatibility**: using `policy.compatibility_rules`, check if the gem's license appears in the compatible list for the project's license. If the project license has no entry in `compatibility_rules`, skip this check. If the gem's license is NOT in the compatible list, emit a `license_incompatibility` finding.
3. **Copyleft in permissive**: if the project's license is in `policy.permissive_licenses` and the gem's license is in `policy.copyleft_licenses`, emit a `copyleft_in_permissive` finding.

## Step 6: Risk Score Computation

Each finding has a risk score computed as:

```
risk_score = severity_multiplier × depth_decay_base ^ depth
```

where `depth` is the resolved gem's depth in the dependency tree (direct = 1), and the severity multiplier and depth decay base come from `policy.risk_score`. Round to `rounding_decimals` places.

For vulnerability findings, use the advisory's severity (not the finding type severity).

## Step 7: Aggregate Risk Score

The summary `aggregate_risk_score` is the **geometric mean** of all individual finding risk scores. The geometric mean of values v₁, v₂, …, vₙ is `exp(mean(ln(v₁), ln(v₂), …, ln(vₙ)))`. Only positive risk scores are included. If there are no findings, aggregate_risk_score is 0.0. Round to 6 decimal places.

## Step 8: Output Sorting

- `project_audits` sorted by `project_id` alphabetically
- `resolved_dependencies` within each audit sorted by `gem_name` alphabetically
- `findings` within each audit sorted by: severity rank ASC, then finding_type ASC, then gem_name ASC
- Global `findings` sorted by: severity rank ASC, then risk_score DESC, then finding_type ASC, then project_id ASC, then gem_name ASC
- `source_hashes` sorted by file path alphabetically

## Step 9: Source Hashes

Compute SHA-256 hashes of every input file under `data/` (registry, projects, config, advisories). The hash is computed on the file content after normalizing line endings to `\n` and stripping a single trailing newline if present. Keys are relative paths from `/app/` (e.g., `data/registry/rack.json`).
