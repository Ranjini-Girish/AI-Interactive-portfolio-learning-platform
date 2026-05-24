# License Compatibility Specification

## License Categories

Permissive: MIT, BSD-3-Clause, Apache-2.0, ISC
Copyleft: GPL-3.0

## Compatibility Rule

A dependency's license is COMPATIBLE with the depending project's license if:

1. The dependency's license is permissive (MIT, BSD-3-Clause, Apache-2.0, ISC) — always compatible regardless of project license.
2. The dependency's license is GPL-3.0 — compatible ONLY if the project's license is also GPL-3.0.

Any unknown or unlisted license is treated as INCOMPATIBLE with all project licenses.

## Transitive License Audit

For each workspace member, check ALL resolved dependencies (direct AND transitive). A dependency is a license violation if the compatibility rule above fails.

## License Audit Result

For each workspace member, produce:
- `license_clean`: boolean — true if ALL deps (direct + transitive) are compatible
- `violations`: sorted array of objects, each with:
  - `crate_name`: the violating crate
  - `crate_license`: its license
  - `project_license`: the workspace member's license
  - `dep_chain`: array of crate names from member to violating crate (inclusive of both endpoints)

Sort violations by crate_name. If multiple chains lead to the same violating crate, report only the SHORTEST chain. If chains are equal length, pick the lexicographically smallest chain (compare element-by-element).
