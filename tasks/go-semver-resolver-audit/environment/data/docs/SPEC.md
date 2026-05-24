# Semantic Version Resolver Specification

## 1. Version Format

A semantic version has the form `MAJOR.MINOR.PATCH` optionally followed by `-PRERELEASE` and/or `+BUILD`.

```
MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
```

- MAJOR, MINOR, PATCH are non-negative integers without leading zeros.
- PRERELEASE is a series of dot-separated identifiers. Each identifier is either numeric (digits only, no leading zeros) or alphanumeric (contains at least one non-digit character).
- BUILD metadata follows `+` and is ignored in all comparisons and constraint matching.

## 2. Version Precedence (Comparison)

When comparing two versions:

1. Compare MAJOR, MINOR, PATCH numerically in that order.
2. A version without pre-release has HIGHER precedence than one with pre-release when MAJOR.MINOR.PATCH are equal. (e.g., 1.0.0 > 1.0.0-rc.1)
3. Pre-release precedence is determined by comparing dot-separated identifiers left to right:
   - Numeric identifiers compare numerically (2 < 11).
   - Alphanumeric (string) identifiers compare lexicographically using ASCII sort order.
   - Numeric identifiers always have LOWER precedence than string identifiers (e.g., 1 < "alpha").
   - A shorter set of identifiers has lower precedence when all preceding identifiers are equal (e.g., "alpha" < "alpha.1").
4. Build metadata is NEVER considered in precedence comparisons.

## 3. Constraint Syntax

A constraint string specifies which versions are acceptable. Supported operators:

### 3.1 Exact Match
- `1.2.3` — matches only version 1.2.3

### 3.2 Comparison Operators
- `>=1.2.3` — greater than or equal
- `<=1.2.3` — less than or equal
- `>1.2.3` — strictly greater
- `<1.2.3` — strictly less

### 3.3 Caret (^) — Compatible with version
The caret allows changes that do not modify the left-most non-zero digit:

- `^1.2.3` := `>=1.2.3, <2.0.0` (major is non-zero, locks major)
- `^0.2.3` := `>=0.2.3, <0.3.0` (major is zero, minor is non-zero, locks minor)
- `^0.0.3` := `>=0.0.3, <0.0.4` (major and minor are zero, locks patch)

### 3.4 Tilde (~) — Patch-level changes
The tilde allows patch-level changes if minor version is specified:

- `~1.2.3` := `>=1.2.3, <1.3.0`
- `~0.2.3` := `>=0.2.3, <0.3.0`
- `~0.0.3` := `>=0.0.3, <0.1.0`

### 3.5 Range (space-separated AND, || for OR)
- `>=1.0.0 <2.0.0` — both conditions must hold (AND)
- `^1.0.0 || ^2.0.0` — either range is acceptable (OR)

## 4. Pre-release Matching Rule

**Critical:** A constraint WITHOUT a pre-release tag does NOT match pre-release versions, even if the pre-release version numerically satisfies the range.

Example: `^1.0.0` (which expands to `>=1.0.0, <2.0.0`) does NOT match `1.0.0-alpha` or `1.0.0-beta`.

Exception: If the constraint comparator itself includes a pre-release on the same `[major, minor, patch]` tuple, then pre-releases on that tuple ARE matched.

Example: `>=1.0.0-beta` DOES match `1.0.0-beta.2` and `1.0.0-rc.1` (same major.minor.patch as the comparator's pre-release). It also matches release versions `1.0.0`, `1.0.1`, `1.1.0`, etc.

However, `>=1.0.0-beta` does NOT match `1.0.1-alpha` (different patch version from the comparator).

## 5. Resolution Algorithm

The resolver processes requests using a Breadth-First-Search (BFS) strategy:

### 5.1 Initialization
1. Read all root constraints from the request.
2. Create a resolution queue with root packages sorted alphabetically by package name.
3. Each entry in the queue has: package name, constraint, depth (root = 1), requester ("ROOT" for root deps).

### 5.2 Processing Loop
For each package in the queue (BFS order, alphabetical within same depth):

1. **Collect constraints:** Gather ALL constraints on this package accumulated so far (from root and transitive dependencies).
2. **Find candidates:** From the registry, find all published versions of this package.
3. **Filter by constraints:** Remove versions that do not satisfy ALL collected constraints (intersection). Apply the pre-release matching rule from §4.
4. **Select version:** Choose the HIGHEST version from the remaining candidates (using precedence from §2).
5. **Check for conflict:** If no candidates remain, record a CONFLICT for this package with the list of incompatible constraints.
6. **Record resolution:** Store the resolved version, depth, and list of requesters.
7. **Enqueue dependencies:** Add the resolved version's dependencies to the queue for the next BFS level, sorted alphabetically. Skip packages already successfully resolved (but verify the existing resolution satisfies the new constraint; if not, record a CONFLICT).

### 5.3 Depth Tracking
- Root packages have depth 1.
- Dependencies of depth-N packages have depth N+1.
- If a package is required by multiple parents at different depths, use the SHALLOWEST depth.

### 5.4 Requester Tracking
- Track all packages that required a given dependency. Store as a sorted list of "package@version" strings.

## 6. Output Format

Produce `/app/output/resolution_report.json` with 2-space indent and trailing newline.

### 6.1 Top-level structure
```json
{
  "schema_version": 1,
  "config": { ... },
  "results": [ ... ]
}
```

### 6.2 Config echo
Echo the config.json values: `max_depth`, `strategy`.

### 6.3 Results array
One entry per request (in the same order as requests.json):

```json
{
  "request_id": "basic",
  "status": "resolved" | "conflict",
  "resolved_packages": [ ... ],
  "conflicts": [ ... ],
  "stats": { ... }
}
```

### 6.4 Resolved package entry
```json
{
  "name": "package-name",
  "version": "1.2.3",
  "depth": 1,
  "requested_by": ["ROOT"] | ["alpha@1.2.1", "beta@0.3.0"],
  "constraint_sources": {
    "ROOT": "^1.2.0",
    "alpha@1.2.1": "^1.0.0"
  }
}
```
Sorted by package name alphabetically.

### 6.5 Conflict entry
```json
{
  "package": "eta",
  "constraints": {
    "gamma@1.1.0": "^1.1.0",
    "kappa@1.1.0": "~1.0.0"
  },
  "reason": "no version satisfies all constraints"
}
```

### 6.6 Stats
```json
{
  "total_resolved": 9,
  "total_conflicts": 0,
  "max_depth": 3,
  "resolution_order": ["alpha", "delta", "epsilon", "beta", ...]
}
```
`resolution_order` lists packages in the order they were resolved (BFS order, alphabetical within level).
