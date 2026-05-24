# Resolver Design Notes

## Resolution Strategy

The resolver uses a "highest compatible" strategy: for each dependency
constraint, it selects the highest version from the registry that falls
within the computed range. If no registry version satisfies a constraint,
the dependency is reported as unresolved.

## Conflict Detection

A cross-project conflict on package P is detected when the intersection
of all version constraints on P (across every project that uses it) is
empty, provided that each individual constraint can be satisfied by at
least one registry version. If any project's constraint on P cannot be
resolved at all, P is reported as unresolved for that project rather
than as a conflict.

## Tie-Breaking

When multiple packages share the same highest usage count in the
`most_depended_package` statistic, the resolver picks the one that
comes first in alphabetical order.

## Output Schema

The report has four top-level keys:

- `conflicts`: array of objects sorted by package name. Each entry has
  `package` (string) and `projects` (map from project name to an object
  with `constraint` and `resolved` strings).
- `metadata`: object with `project_count`, `registry_package_count`,
  and `registry_version_count`.
- `resolutions`: map from project name to an object with `resolved`
  (map of dependency name to version string) and `unresolved` (sorted
  array of package names that could not be resolved).
- `statistics`: object with `conflict_count`, `most_depended_count`,
  `most_depended_package`, `projects_fully_resolved`,
  `projects_with_unresolved`, and `total_unique_dependencies`.

## Output Format

The JSON report uses sorted keys at every nesting level, 2-space
indentation, and a single trailing newline character.
