# Version Constraint Semantics

This document describes the exact version constraint matching rules used by the resolver. These follow standard RubyGems semantics.

## Version Ordering

A version string is split into segments by `.` characters. Each segment is either numeric (compared as integers) or alphabetic (compared as strings). A numeric segment is always greater than an alphabetic segment when compared directly. For example, `1.0.0` > `1.0.rc1` because the third segment `0` (numeric) is greater than `rc1` (alphabetic).

Pre-release versions contain at least one alphabetic segment after the last numeric-only sequence. Pre-release versions of a release are less than that release: `2.0.0.beta1` < `2.0.0`.

### Comparison Algorithm

Given two versions A and B, split each into segments. Compare segments pairwise left to right:

1. If both segments are numeric, compare as integers.
2. If both segments are alphabetic, compare as strings (lexicographic, case-sensitive).
3. If one is numeric and the other is alphabetic, the numeric segment is greater.
4. If one version has more segments than the other, missing segments on the shorter version are treated as segment `0` when comparing against a numeric segment, or as empty string when comparing against an alphabetic segment. However, a version with fewer segments that are all numeric is GREATER than an extended version with an alphabetic segment: `1.0` > `1.0.alpha`.

### Pre-release Detection

A version is pre-release if any segment after the first segment is alphabetic. Examples:
- `1.0.0.rc1` — pre-release (segment `rc1` is alphabetic)
- `1.0.0.beta` — pre-release
- `1.8.3.pre.beta` — pre-release (segment `pre` is alphabetic)
- `2.2.0.alpha` — pre-release
- `2.2.0` — stable release
- `1.0.0` — stable release

## Constraint Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `= X` | Exactly version X | `= 2.1.0` matches only `2.1.0` |
| `!= X` | Any version except X | `!= 2.1.0` matches everything but `2.1.0` |
| `> X` | Strictly greater than X | `> 2.1.0` matches `2.1.1`, `2.2.0`, `3.0.0`, etc. |
| `>= X` | Greater than or equal to X | `>= 2.1.0` matches `2.1.0`, `2.1.1`, `2.2.0`, etc. |
| `< X` | Strictly less than X | `< 3.0.0` matches `2.9.9`, `2.2.3`, etc. |
| `<= X` | Less than or equal to X | `<= 2.2.3` matches `2.2.3`, `2.2.0`, `2.1.0`, etc. |
| `~> X.Y.Z` | Pessimistic (3+ segments) | `~> 2.2.0` is equivalent to `>= 2.2.0` AND `< 2.3.0` |
| `~> X.Y` | Pessimistic (2 segments) | `~> 2.1` is equivalent to `>= 2.1.0` AND `< 3.0.0` |

## The Pessimistic Operator (`~>`)

The pessimistic constraint operator `~>` (called "twiddle-wakka") allows the last specified segment to increment but locks all earlier segments. Formally, it increments the **second-to-last** segment by 1 and drops the last segment to form the upper bound.

### Two-segment form: `~> X.Y`

This means `>= X.Y.0` AND `< (X+1).0.0`. The second-to-last segment is X (the major version), which gets incremented.

Examples:
- `~> 2.1` means `>= 2.1.0, < 3.0.0` — allows `2.1.0`, `2.2.0`, `2.9.5`, but NOT `3.0.0`
- `~> 1.8` means `>= 1.8.0, < 2.0.0` — allows `1.8.0`, `1.9.3`, but NOT `2.0.0`
- `~> 0.9` means `>= 0.9.0, < 1.0.0`

### Three-segment form: `~> X.Y.Z`

This means `>= X.Y.Z` AND `< X.(Y+1).0`. The second-to-last segment is Y (the minor version), which gets incremented.

Examples:
- `~> 2.2.0` means `>= 2.2.0, < 2.3.0` — allows `2.2.0`, `2.2.3`, but NOT `2.3.0`
- `~> 3.1.0` means `>= 3.1.0, < 3.2.0`
- `~> 1.14` (two segments) means `>= 1.14.0, < 2.0.0`

### Four-segment form: `~> X.Y.Z.W`

This means `>= X.Y.Z.W` AND `< X.Y.(Z+1).0`. The second-to-last segment is Z (patch), which gets incremented.

Example:
- `~> 4.9.0` (three segments) means `>= 4.9.0, < 4.10.0`

## Pre-release Exclusion

When evaluating constraints, pre-release versions are excluded from matching unless the constraint itself explicitly references a pre-release version. For instance, `>= 2.0` does NOT match `2.2.0.alpha`. Only if the constraint is something like `>= 2.2.0.alpha` would pre-release versions be considered.

## Multiple Constraints

When a gem has multiple constraints (from different dependents), a version must satisfy ALL of them simultaneously. The resolver picks the highest stable version that satisfies the intersection of all active constraints.
