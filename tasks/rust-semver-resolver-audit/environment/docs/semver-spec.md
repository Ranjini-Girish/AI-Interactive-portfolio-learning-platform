# Semantic Versioning 2.0.0 — Quick Reference

A version number has the form MAJOR.MINOR.PATCH with optional pre-release
and build metadata suffixes: `MAJOR.MINOR.PATCH[-pre][+build]`.

## Precedence

Versions are compared by major, then minor, then patch. When those are
equal, a version with a pre-release suffix has lower precedence than the
same version without one (e.g. `1.0.0-alpha < 1.0.0`).

Pre-release identifiers are compared left to right:

- Numeric identifiers are compared as integers.
- Alphanumeric identifiers are compared lexicographically (ASCII).
- Numeric identifiers always have lower precedence than alphanumeric ones.
- A shorter set of pre-release identifiers has lower precedence when all
  preceding identifiers are equal.

Build metadata (`+...`) is ignored for version precedence.

## Caret Ranges

`^X.Y.Z` allows changes that do not modify the left-most non-zero digit:

| Constraint | Equivalent range         |
|------------|--------------------------|
| `^1.2.3`   | `>=1.2.3, <2.0.0`       |
| `^0.2.3`   | `>=0.2.3, <0.3.0`       |
| `^0.0.3`   | `>=0.0.3, <0.0.4`       |
| `^1.2`     | `>=1.2.0, <2.0.0`       |
| `^0.0`     | `>=0.0.0, <0.1.0`       |

## Tilde Ranges

`~X.Y.Z` allows only patch-level changes:

| Constraint | Equivalent range         |
|------------|--------------------------|
| `~1.2.3`   | `>=1.2.3, <1.3.0`       |
| `~1.2`     | `>=1.2.0, <1.3.0`       |
| `~0.2.3`   | `>=0.2.3, <0.3.0`       |

## Exact

`=X.Y.Z` matches only the specified version.
