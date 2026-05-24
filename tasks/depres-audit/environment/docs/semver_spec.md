# Semantic Versioning Specification

## Version Format

MAJOR.MINOR.PATCH with optional pre-release: `1.0.0-alpha.1`

## Version Ordering

Pre-release has LOWER precedence than release: `1.0.0-beta < 1.0.0`. Numeric identifiers sort before alphanumeric: `1.0.0-1 < 1.0.0-alpha`.

## Caret Range (`^`)

Allows changes that do not modify the left-most non-zero digit:
- `^1.2.3` := `>=1.2.3, <2.0.0`
- `^0.2.3` := `>=0.2.3, <0.3.0`
- `^0.0.3` := `>=0.0.3, <0.0.4`
- `^0.2` := `>=0.2.0, <0.3.0`

## Tilde Range (`~`)

Allows patch-level changes only:
- `~1.2.3` := `>=1.2.3, <1.3.0`
- `~1.0` := `>=1.0.0, <1.1.0`
- `~0.4.17` := `>=0.4.17, <0.5.0`

## Pre-Release Matching

Stable ranges do NOT match pre-release versions. `^1.0` does not match `1.0.0-beta.1`.

## Resolution

Select the HIGHEST compatible version.
