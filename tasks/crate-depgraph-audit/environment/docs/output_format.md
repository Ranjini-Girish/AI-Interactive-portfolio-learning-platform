# Output Format Specification

The output file is `/app/output/resolver_report.json`.

## Top-Level Structure

```json
{
  "checksums": { ... },
  "conflicts": [ ... ],
  "findings": [ ... ],
  "metrics": { ... },
  "resolved": [ ... ]
}
```

Keys at ALL levels are sorted alphabetically. The file uses 2-space
indentation and ends with a trailing newline (`\n`).

## `resolved` Array

Each entry represents one resolved crate:

```json
{
  "name": "crate-name",
  "version": "X.Y.Z",
  "depth": <integer>,
  "features": ["feat1", "feat2"],
  "dependents": ["crate-a", "crate-b"],
  "license": "license string"
}
```

- `features`: alphabetically sorted list of all enabled features. Entries of
  the form `dep:X` are internal activation directives and must NOT appear in
  this list — only named features (e.g., `"default"`, `"std"`, `"v4"`) are included.
- `dependents`: alphabetically sorted list of crate names that depend on
  this crate. Use `"my-app"` for the root manifest.
- The array is sorted by `name` (ascending).

## `conflicts` Array

Each entry (if any):

```json
{
  "name": "crate-name",
  "constraints": ["^1.0 (from X)", "~1.2 (from Y)"],
  "available_versions": ["1.0.0", "1.1.0", "1.2.0"]
}
```

Sorted by `name`.

## `metrics` Object

```json
{
  "avg_depth": <float, 4 decimal places>,
  "direct_dependencies": <integer>,
  "max_depth": <integer>,
  "total_crates": <integer>,
  "total_features_enabled": <integer>,
  "transitive_dependencies": <integer>
}
```

- `total_crates`: number of entries in `resolved`.
- `direct_dependencies`: crates at depth 1.
- `transitive_dependencies`: total_crates - direct_dependencies.
- `max_depth`: highest depth value in `resolved`.
- `avg_depth`: arithmetic mean of all depth values, rounded to 4 decimal places.
- `total_features_enabled`: sum of feature list lengths across all resolved crates.

## `findings` Array

Security advisory matches:

```json
{
  "advisory_id": "RUSTSEC-XXXX-YYYY",
  "crate": "crate-name",
  "severity": "critical|high|medium|low",
  "title": "advisory title",
  "type": "advisory",
  "version": "X.Y.Z"
}
```

Sorted by: severity (critical > high > medium > low), then `crate` name ascending.

An advisory applies to a resolved crate only if its version satisfies ALL
bounds in the `affected_versions` field. Advisories for crates not in the
resolved set are ignored.

## `checksums` Object

SHA-256 hex digests (lowercase) of raw file bytes for each input file.
Keys are relative paths from `/app/` (e.g., `"data/manifest.json"`).

Include:
- `data/manifest.json`
- `data/advisories.json`
- All files in `data/registry/` (sorted by filename)

Keys are sorted alphabetically.
