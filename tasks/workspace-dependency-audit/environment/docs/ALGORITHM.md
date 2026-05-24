# Audit Algorithm Specification

## Input

- **Registry**: JSON files in `data/registry/`, one per package.
- **Workspace**: Directories in `data/workspace/`, each containing a `package.json`.
- **Policy**: `data/workspace/policy.json` with license rules, severity config, and risk scoring.
- **Advisories**: `data/workspace/advisories.json` with known vulnerability entries.

## Processing Order

1. **Load workspace packages** sorted alphabetically by directory name.
2. **Resolve dependencies** for each package (only `dependencies` from `scope_filter`, NOT `devDependencies`).
3. **Detect workspace cycles**: Build a directed graph of workspace inter-dependencies. A cycle exists if any package transitively depends on itself through workspace links.
4. **Resolve external versions**: For each external dependency, find the highest matching version from the registry.
5. **Build full dependency graph**: Including transitive dependencies from resolved packages (using their registry metadata).
6. **Compute hoisting analysis**: Determine which dependencies can be hoisted.
7. **Detect phantom dependencies**: Scan source files for undeclared requires.
8. **Match advisories**: Check resolved versions against advisory affected ranges.
9. **Evaluate license compatibility**: Check each resolved dependency's license against the workspace package's own license using `compatibility_rules`.
10. **Generate findings**: One finding object per issue detected.
11. **Compute metrics**: Summary statistics.

## Dependency Graph Depth

For each resolved dependency, compute its depth in the dependency graph starting from the workspace package root (depth 0). A direct dependency is depth 1. A transitive dependency of a depth-1 dep is depth 2, etc.

Use BFS from each workspace package to compute depths. If a package is reachable at multiple depths, use the MINIMUM depth.

## Metrics

- **total_dependencies**: Count of unique external packages resolved across ALL workspace packages (deduplicated by name — if the same package appears in multiple workspace packages, count it once).
- **total_findings**: Total number of finding objects generated.
- **avg_depth**: Harmonic mean of all resolved dependency depths across all workspace packages. Formula: `n / sum(1/d for d in depths)` where `n` is the count of all (workspace_pkg, dep, depth) tuples where depth > 0. Exclude depth-0 entries. Round to 4 decimal places.
- **aggregate_risk_score**: Geometric mean of all finding risk scores. Formula: `(product of all risk_scores) ^ (1/n)`. Round to 4 decimal places. If no findings, use `0.0`.
- **hoistable_count**: Number of external packages that CAN be hoisted to root.
- **conflict_count**: Number of external packages that CANNOT be hoisted due to version conflicts.

## Risk Score per Finding

`risk_score = severity_multiplier * (depth_weight_base ^ depth)`

Where:
- `severity_multiplier` is from `policy.risk_score.severity_multipliers[severity]`
- `depth` is the minimum depth of the affected dependency from the affected workspace package
- For workspace-level findings (cycles), use depth = 0
- Round to `policy.risk_score.rounding_decimals` decimal places

## Finding Object Structure

Each finding has:
- `finding_id`: `"F-{sequential_number:03d}"` starting from F-001
- `category`: one of the `finding_severity` keys
- `severity`: from `policy.finding_severity[category]`
- `package`: the affected workspace package directory name
- `dependency`: the external dependency name (or workspace package for cycles)
- `detail`: descriptive string (see below)
- `risk_score`: computed per formula above

## Finding Generation Order

Generate findings in this order (which determines IDs):
1. Workspace cycles (sorted by package name alphabetically)
2. Version conflicts (sorted by dependency name, then package name)
3. Phantom dependencies (sorted by package name, then dependency name)
4. License incompatibilities (sorted by package name, then dependency name)
5. Advisory matches (sorted by advisory ID, then package name)
6. Hoisting conflicts (sorted by dependency name)

## Detail Strings

- **workspace_cycle**: `"{pkg_a} -> {pkg_b} -> ... -> {pkg_a}"` showing the cycle path
- **version_conflict**: `"No version of {dep} satisfies {constraint} in {package}"`
- **phantom_dependency**: `"{dep} used in {package}/src/{file} but not declared"`
- **license_incompatibility**: `"{dep}@{version} ({dep_license}) incompatible with {package} ({pkg_license})"`
- **advisory_match** (uses category `phantom_dependency`... NO. Use `"deprecated_range"` for advisories): Actually, advisories don't map to a standard category. Use a special rule: advisory findings use the advisory severity directly, NOT from `finding_severity`. Category is `"vulnerability"`. Wait, that's not in the enum...

Let me reconsider. Actually, for advisory matches: the category field is set to the advisory's severity (e.g., "high", "medium"), and severity_multiplier comes from the same advisory severity. The finding uses `finding_severity` only for the standard categories. For advisory matches specifically:
- `category`: `"vulnerability"`  
- `severity`: The advisory's own severity field
- `detail`: `"{advisory_id}: {description} ({dep}@{version} in {package})"`

Wait, `vulnerability` is not in `finding_severity`. That's fine — advisory findings use the advisory's severity directly to look up `severity_multipliers`.

## Hoisting Conflicts Detail

- `"hoisting_conflict"`: `"{dep} cannot be hoisted: {pkg_a} needs {version_a}, {pkg_b} needs {version_b}"` listing all conflicting packages sorted alphabetically.

## Output

Write to `/app/output/workspace_audit.json`:
- All keys sorted alphabetically at every nesting level
- 2-space indentation
- Trailing newline
- Floats rounded to 4 decimal places

## Top-Level Output Structure

```json
{
  "dependency_graph": { ... },
  "findings": [ ... ],
  "hoisting": { ... },
  "metadata": { ... },
  "summary": { ... }
}
```

### metadata
```json
{
  "evaluation_date": "2026-05-14",
  "scope": "dependencies",
  "source_hash": "<sha256>",
  "workspace_packages": ["pkg-api", "pkg-auth", "pkg-cli", "pkg-core", "pkg-utils"]
}
```

`source_hash`: SHA-256 of the concatenation of all workspace `package.json` files in sorted directory order, each file read as-is (raw bytes).

### dependency_graph

Object mapping each workspace package directory name to its resolved dependencies:
```json
{
  "pkg-core": {
    "lodash": {"depth": 1, "version": "4.17.21"},
    "uuid": {"depth": 1, "version": "9.0.0"},
    "zod": {"depth": 1, "version": "3.22.4"}
  },
  ...
}
```

### hoisting

```json
{
  "conflicts": ["axios", "dotenv"],
  "hoistable": ["bcrypt", "body-parser", ...]
}
```

Both arrays sorted alphabetically.

### summary

```json
{
  "aggregate_risk_score": 5.1234,
  "avg_depth": 1.2345,
  "conflict_count": 2,
  "hoistable_count": 10,
  "total_dependencies": 14,
  "total_findings": 8
}
```
