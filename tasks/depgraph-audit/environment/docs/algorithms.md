# Dependency Resolution & Audit Algorithms

## 1. Semantic Version Parsing

Parse versions as `MAJOR.MINOR.PATCH` optionally followed by `-PRERELEASE`.

Pre-release strings are split on `.` into identifiers.  Each identifier is
classified as **numeric** (all digits, no leading zeros except `"0"` itself) or
**string** (anything else).

### 1.1 Version Comparison

Standard semver 2.0.0 precedence:

1. Compare MAJOR, MINOR, PATCH numerically.  Higher wins.
2. A version *without* pre-release has **higher** precedence than the same
   MAJOR.MINOR.PATCH *with* a pre-release.  E.g. `1.1.0 > 1.1.0-rc.1`.
3. Pre-release identifiers are compared left-to-right:
   - **Numeric vs numeric** → compare as integers.  `11 > 2`.
   - **String vs string** → compare lexicographically (byte-order).
   - **Numeric vs string** → numeric **always** has lower precedence.
     `1.0.0-1 < 1.0.0-alpha`.
   - **Fewer identifiers** → fewer < more when all preceding identifiers are
     equal.  `1.1.0-beta < 1.1.0-beta.2`.

### 1.2 Pre-release Version Ranges

The `prerelease_policy` is `"explicit_only"`.  This means a `>=` constraint
matches a pre-release **only** if the constraint itself names a pre-release
with the **same** MAJOR.MINOR.PATCH base.

- `>= 1.1.0` matches `1.1.0`, `1.2.0`, `2.0.0`, … but **NOT** `1.1.0-beta`.
- `>= 1.1.0-beta` matches `1.1.0-beta`, `1.1.0-beta.2`, `1.1.0-beta.11`,
  `1.1.0-rc.1`, `1.1.0`, `1.2.0`, ….  It does **NOT** match `1.1.0-alpha`
  (alpha < beta).
- `>= 1.1.0-beta.2` matches `1.1.0-beta.2`, `1.1.0-beta.11`, `1.1.0-rc.1`,
  `1.1.0`, `1.2.0`, ….

## 2. Minimum Version Selection (MVS)

This is the **core** resolution algorithm.  It is fundamentally different from
"latest compatible" resolvers (npm, pip, cargo).

### 2.1 Algorithm

Given a set of root `requirements` (each is a module path + minimum version):

```
resolved = {}   // module_path → resolved_version
queue    = copy(root_requirements)

while queue is not empty:
    pick any (module, min_ver) from queue
    
    if module already in resolved:
        existing = resolved[module]
        if existing >= min_ver:
            continue   // already satisfied
        // else need upgrade — set to max(existing, min_ver)
    
    // Find the MINIMUM available version V of module such that V >= min_ver,
    // V is not in the exclude list for this query, and
    // V satisfies the pre-release policy (see §1.2).
    // If no such version exists → resolution error.
    
    resolved[module] = V
    
    // Add all dependencies of module@V to the queue.
    for each (dep_module, dep_min_ver) in deps_of(module, V):
        queue.add( (dep_module, dep_min_ver) )

// Repeat until no changes propagate (fixed-point).
```

**Critical**: when a module is upgraded from one version to another during
propagation, its **new** version's dependencies must replace the old ones.
Re-enqueue all dependencies of the new version.

### 2.2 Convergence

Run the algorithm to a fixed point.  In each iteration, if any module's
resolved version increases, re-process that module's dependencies.  The
algorithm terminates because versions can only increase and the set of
available versions is finite.

## 3. Exclude Directives

A query may list excluded `(module, version)` pairs.  An excluded version
is **skipped** during selection.  If MVS would select version V and V is
excluded, select the **next higher** available version that satisfies the
constraint and pre-release policy.

If no such version exists, the resolution fails for that module —
record a finding of type `"resolution_error"` with severity `"critical"`.

## 4. Replace Directives

A query may list replace directives of the form:

```json
{"old_module": "A", "new_module": "B", "new_version": "V"}
```

This means: wherever the resolution would resolve module `A`, instead use
module `B` at version `V`.  

Specifics:
- The **replaced module** (`A`) no longer appears in `resolved_modules`.
  Instead, `B@V` appears.
- The dependency tree entry uses key `"B@V"` where it would have used `"A@..."`.
- The **dependencies** of the replacement are those of `B@V` from the
  registry, **not** those of any version of `A`.
- If `B@V` does not exist in the registry → resolution error finding.
- Other modules that depend on `A` now effectively depend on `B@V`.
  Their `min_version` constraint on `A` is **ignored** (the replace
  pins to exactly `V`).

## 5. Cycle Detection

After resolution, build the dependency graph.  Detect all **simple cycles**.
Report each cycle as the **sorted list of module paths** involved.

If multiple cycles exist, report them all.  Each cycle is represented as
the list of module paths sorted lexicographically, starting from the
lexicographically smallest module.

## 6. Build Order (Topological Sort)

Compute a topological ordering of the resolved dependency graph using
**Kahn's algorithm** with a **min-heap** for tie-breaking:

1. Compute in-degree of each module (count of dependencies within the
   resolved set).
2. Initialize a min-heap with all modules having in-degree 0.
   The heap key is the **full module path** (lexicographic ordering).
3. Repeatedly extract the minimum from the heap, append to build order,
   and decrement in-degrees of dependents.  When a dependent reaches
   in-degree 0, push it onto the heap.

If cycles exist, the build order includes only modules that are **not**
part of any cycle.  Cyclic modules are omitted from build_order and
listed separately in the `cycles` field.

## 7. Depth Analysis

Compute the **maximum depth** of the resolved dependency graph.

Depth of a module = 0 if it has no dependencies (within the resolved set),
otherwise 1 + max(depth of each dependency).

The `max_depth` field is the maximum depth across all resolved modules.

## 8. Vulnerability Checking

For each resolved module@version, check against the vulnerability database.
A version V is affected by a vulnerability if:

    affected_min <= V    AND    V < affected_max

Note: `affected_min` is **inclusive**, `affected_max` is **exclusive**.

Use semantic version comparison (§1), **not** string comparison.

Pre-release versions of `affected_max` are treated as less than the
release.  E.g. if affected_max is "2.0.0", then "2.0.0-rc.1" **is**
affected (it is < 2.0.0).

## 9. License Compatibility

The query specifies a `project_license`.  For each resolved module@version,
look up its license.  Check whether that license appears in the
`license_compatibility[project_license]` list from `config/audit.json`.

If the dependency license is **not** in the allowed list → license
incompatibility finding.

## 10. Retracted Versions

Each module definition may list `retracted` versions.  If any resolved
module@version is in the module's `retracted` list, emit a finding of
type `"retracted_version"`.

## 11. Source Integrity

Compute SHA-256 hashes of every input file under `config/`, `data/`, and
`docs/`.  Store in the `source_sha256` map as `relative_path → hex_digest`.
Paths are relative to `/app/` and use forward slashes.  Sort keys
lexicographically.

## 12. Summary

The `summary` object contains:
- `total_queries`: number of queries processed
- `total_modules_resolved`: sum of unique modules resolved across all queries
- `total_vulnerabilities_found`: count of vulnerability matches across all queries
- `total_license_issues`: count of license incompatibility findings
- `total_cycles`: count of distinct cycles detected
- `findings_by_severity`: map from severity name to count, **including all
  five levels** (critical, high, medium, low, info) even if count is 0
