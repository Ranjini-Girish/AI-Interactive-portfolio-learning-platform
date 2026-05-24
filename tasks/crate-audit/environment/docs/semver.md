# Semantic Versioning Specification

## Version Format

A version has the form MAJOR.MINOR.PATCH with an optional pre-release suffix:

    MAJOR.MINOR.PATCH[-PRERELEASE]

Examples: 1.0.0, 2.3.1, 0.1.0-beta.1, 1.0.0-rc.10

## Version Comparison

Versions are compared by MAJOR, MINOR, PATCH in that order. When all three components are equal, the pre-release suffix determines ordering.

A version without a pre-release suffix has HIGHER precedence than any version with the same MAJOR.MINOR.PATCH and a pre-release suffix. For example, 1.0.0 > 1.0.0-rc.1.

### Pre-release Comparison

Pre-release identifiers are separated by dots and compared left to right using standard comparison for each identifier's type. A version with fewer pre-release identifiers has lower precedence when all preceding identifiers are equal.

## Constraint Operators

### Exact (=)

`=1.2.3` matches only version 1.2.3.

### Comparison (>=, >, <=, <)

Standard numeric comparison. Pre-release versions follow the ordering rules above.

### Caret (^)

The caret allows changes that do not modify the left-most non-zero digit:

- `^1.2.3` is equivalent to `>=1.2.3, <2.0.0`
- `^0.2.3` is equivalent to `>=0.2.3, <0.3.0`

This permits patch and minor updates while maintaining compatibility.

### Tilde (~)

The tilde allows patch-level changes:

- `~2.1.0` is equivalent to `>=2.1.0, <2.2.0`
- `~1.0.0` is equivalent to `>=1.0.0, <1.1.0`

### Compound Constraints

Multiple constraints can be combined with commas: `>=1.0.0-rc.1, <1.0.0` means the version must satisfy both constraints simultaneously.

## Resolution Rule

When multiple versions satisfy a constraint, the resolver selects the highest matching version. When a package is required by multiple dependents with different constraints, the resolver intersects all constraints and selects the highest version satisfying all of them.
