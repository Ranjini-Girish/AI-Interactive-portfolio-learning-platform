# Minimal Version Selection (MVS) Specification

## Overview

This resolver uses Go-style Minimal Version Selection. Unlike most package managers that choose the **newest** version satisfying constraints, MVS selects the **minimum** (oldest) version that satisfies all requirements across the entire dependency graph.

## Algorithm

1. Start with each root module and its declared version.
2. For each dependency constraint `>=X.Y.Z`, record X.Y.Z as a **requirement**.
3. Walk the dependency graph breadth-first. When the same package is required by multiple dependents, take the **maximum** of all minimum requirements — this is the "minimum version that satisfies all constraints."
4. The selected version for each package is: `max(all minimum requirements for that package)`.

## Semver Ordering

Versions follow Semantic Versioning 2.0.0 ordering:

- Compare major, then minor, then patch numerically.
- A version with a pre-release tag (e.g., `1.4.0-beta.1`) sorts **before** the same version without a tag (`1.4.0`). This means `1.4.0-beta.1 < 1.4.0`.
- Pre-release identifiers are compared left to right. Numeric identifiers compare as integers; alphanumeric identifiers compare lexicographically (ASCII). Numeric identifiers always sort before alphanumeric identifiers.
- Examples: `1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-rc.1 < 1.0.0`

## Pre-release Exclusion Policy

When `prerelease_policy` is `"exclude"`, pre-release versions are **not considered** during resolution unless the constraint explicitly references a pre-release version. A constraint like `>=1.2.0` will **not** match `1.4.0-beta.1`.

## Constraint Syntax

- `>=X.Y.Z` — minimum version (inclusive). Select the smallest available version that is >= X.Y.Z and satisfies the pre-release policy.

## Resolution Output

For each resolved package, record:
- `package`: package name
- `version`: resolved version string
- `required_by`: sorted list of packages that directly depend on this package
- `depth`: shortest path distance from any root module (root modules have depth 0, their direct dependencies have depth 1, etc.)
- `constraint_path`: the chain of packages from the root that caused this version to be selected (the path that imposed the highest minimum requirement)

## Conflict Handling

If no available version satisfies a constraint, the package is marked as `"unresolved"` in the output with the unsatisfied constraint recorded.
