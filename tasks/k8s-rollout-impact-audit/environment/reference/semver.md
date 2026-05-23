# Semver — what counts as a valid version

A version is **valid** for this task only when it is a string of exactly three dot-separated non-negative integer parts:

- `0.0.0`, `1.2.3`, `10.20.30` — valid.
- `1.0`, `1.0.0.0`, `v1.0.0`, `1.0.0-rc1`, `1.0.0+meta`, `2.x.0`, `1.-1.0` — invalid.

Pre-release suffixes, build-metadata suffixes, leading `v`, two-segment versions, and four-segment versions are all rejected. Comparison is by the `(major, minor, patch)` integer tuple.

Invalid versions are silently dropped wherever they appear: registry entries, `release.require`, `release.replace.from` / `to`, `release.exclude`, child `require` arrays, and `workload_dependency_map.json` values.
