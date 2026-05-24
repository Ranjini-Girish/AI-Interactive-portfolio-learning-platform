# Semver Constraint Resolution

This document defines the exact version constraint semantics used by the workspace auditor.

## Version Comparison

Versions follow semantic versioning: `MAJOR.MINOR.PATCH`. Pre-release versions (containing a hyphen, e.g., `1.0.0-beta.1`) are excluded from all constraint matching.

Compare versions segment by segment as integers: major first, then minor, then patch.

## Constraint Operators

### Caret (`^`)

The caret operator allows changes that do not modify the leftmost non-zero digit.

- `^1.2.3` means `>=1.2.3` and `<2.0.0` — locks the major version.
- `^0.2.3` means `>=0.2.3` and `<0.3.0` — when major is 0, locks the minor version.
- `^0.0.3` means `>=0.0.3` and `<0.0.4` — when major and minor are 0, locks the patch.

### Tilde (`~`)

The tilde operator allows patch-level changes only.

- `~1.2.3` means `>=1.2.3` and `<1.3.0` — always locks at the minor level.
- `~0.2.3` means `>=0.2.3` and `<0.3.0` — same rule regardless of major being 0.

### Exact (`x.y.z` with no operator)

Matches exactly that version.

### Star (`*`)

Matches any version. Select the highest available.

### Range operators (`>=`, `>`, `<`, `<=`)

Standard comparison. Multiple constraints separated by space are AND-ed together.

## Workspace Protocol

The `workspace:*` specifier means the dependency is satisfied by the local workspace package at its declared version. It is NOT resolved from the registry.

## Resolution Strategy

For each dependency, pick the highest version from the registry that satisfies the constraint. If no version satisfies, record a version conflict finding.

Process workspace packages in alphabetical order by their directory name.

## Hoisting Analysis

A dependency can be hoisted to the workspace root if ALL workspace packages that depend on it resolve to the same version. If different packages resolve different versions of the same dependency, a hoisting conflict exists.

## Phantom Dependencies

A phantom dependency occurs when a package's source files import a module that is NOT declared in that package's own `dependencies` but IS available because another workspace package depends on it. For this analysis, check each package's `src/` files for `require('...')` or `require("...")` calls. If the required module is not in the package's own dependencies (or devDependencies) and is not a relative path (starting with `.` or `/`), and is not a workspace package, it is a phantom dependency.

## Advisory Matching

An advisory applies to a resolved dependency if:
- The advisory's `package` field matches the dependency name
- The resolved version satisfies the advisory's `affected_range` constraint

The `affected_range` uses the same constraint syntax described above.
