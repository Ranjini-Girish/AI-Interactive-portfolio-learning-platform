# Edge Cases

## 1. Pre-release Numeric Ordering

Pre-release identifiers that are purely numeric must be compared as integers,
not as strings.  `beta.11 > beta.2` because `11 > 2` numerically.

If compared lexicographically, `"11" < "2"` which gives wrong ordering.

## 2. Pre-release Range Matching

With `prerelease_policy: "explicit_only"`:
- `>= 1.1.0` does NOT match `1.1.0-beta`, because the constraint has no
  pre-release and 1.1.0-beta has a different (lower) base.
- `>= 1.1.0-beta.2` DOES match `1.1.0-beta.11` (same base, higher pre).
- `>= 1.1.0-beta.2` does NOT match `1.0.9` (different MAJOR.MINOR.PATCH,
  but 1.0.9 is a release with higher M.m.p?). Actually, `1.0.9 < 1.1.0-beta.2`
  since `1.0 < 1.1`, so it does not satisfy `>=`.

## 3. MVS Selects Minimum, Not Latest

If available versions are [1.0.0, 1.1.0, 1.2.0, 2.0.0] and the constraint
is `>= 1.1.0`, MVS selects **1.1.0**, not 2.0.0.

Latest-compatible resolvers would pick 2.0.0.  This is the single most
common mistake.

## 4. MVS Upgrade Propagation

When module A's resolved version is upgraded (e.g., from 1.1.0 to 1.2.0)
because of a transitive constraint, module A's **new** dependencies (those
of 1.2.0) must be re-processed.  The old dependencies (from 1.1.0) are
discarded.

## 5. Exclude Bumps to Next Higher

If MVS selects version V and V is excluded, pick the next available version
**above** V (not below).  If 1.1.0 is excluded and candidates are
[1.0.0, 1.1.0, 1.2.0], MVS selects 1.2.0 (skip 1.1.0, take next).

## 6. Replace Overrides Everything

A replace directive pins the module to exactly the replacement version.
Even if the original module was required at `>= 2.0.0`, the replace
ignores this constraint and uses the specified replacement module@version.

The replaced module's path is removed from `resolved_modules`.  The
replacement module's path appears instead.

## 7. Cycles Don't Block Resolution

If the dependency graph contains cycles, resolution still completes
(MVS converges to a fixed point).  Cycles are detected and reported
**after** resolution.  Cyclic modules are excluded from `build_order`
but still appear in `resolved_modules` and `dependency_tree`.

## 8. Vulnerability Boundary

`affected_max` is **exclusive**.  If `affected_max` = "2.0.0" and the
resolved version is "2.0.0", it is NOT affected.  If the resolved version
is "1.9.9", it IS affected.

Pre-releases of `affected_max` are less than the release:
"2.0.0-rc.1" < "2.0.0", so "2.0.0-rc.1" IS affected when
`affected_max` = "2.0.0".

## 9. License Matrix Is Not Symmetric

The compatibility matrix in `config/audit.json` is directional:
`license_compatibility[project_license]` lists allowed **dependency**
licenses.

`Apache-2.0` allows `MIT` as a dependency, but `MIT` does NOT allow
`Apache-2.0` as a dependency.  Read the matrix carefully.

## 10. Empty/Missing Fields

- If no vulnerabilities match a query → `vulnerabilities` is `[]`.
- If no cycles → `cycles` is `[]`.
- If no license issues → `license_issues` is `[]`.
- If no resolution errors → `resolution_errors` is `[]`.
- If no retracted versions used → `retracted_warnings` is `[]`.
- The `findings_by_severity` map **always** has all 5 severity keys.

## 11. Multiple Vulnerabilities Per Module

A single resolved module@version can match multiple vulnerability entries.
Each match is a separate entry in `vulnerabilities`.

## 12. Retracted Versions Are Still Available

Retracted versions are valid for resolution.  They are just flagged.
Do not skip them during MVS selection (unlike excluded versions).

## 13. Build Order With No Dependencies

If a query resolves only one module with no deps, `build_order` is `["<that_module>"]`
and `max_depth` is `0`.

## 14. Depth With Cycles

For cyclic dependency chains, use a visited marker during depth computation.
If a module is encountered again during its own recursive depth computation,
treat its depth contribution through that cyclic edge as **0** (sentinel).
Process modules in **lexicographic order** of their paths for deterministic
results.
