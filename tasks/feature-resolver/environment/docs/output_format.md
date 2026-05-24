# Output Format

Write JSON to `/app/output/build_plan.json` with **2-space indentation**
and a **trailing newline**.

## Top-Level Schema

```json
{
  "workspace": { ... },
  "resolved_crates": [ ... ],
  "dependency_graph": { ... },
  "cycles": { ... },
  "build_order": [ ... ],
  "build_checksum": "...",
  "size_analysis": { ... },
  "findings": { ... }
}
```

Keys must appear in exactly this order.

## `workspace`

```json
{
  "name": "acme-platform",
  "version": "3.1.0",
  "root_crate": "app-server",
  "total_crates": 23,
  "reachable_crates": 22
}
```

## `resolved_crates`

A sorted array (by crate `name` ascending) of objects:

```json
{
  "name": "some-crate",
  "version": "1.0.0",
  "reachable": true,
  "resolved_features": ["default", "feat-a", "feat-b"],
  "activated_optional_deps": ["opt-dep-name"],
  "resolved_dependencies": ["dep-a", "dep-b"],
  "depth": 3,
  "fan_in": 2,
  "fan_out": 1,
  "instability": 0.333333,
  "active_size": 1234.567890,
  "layer": "internal",
  "total_exports": 5
}
```

- `resolved_features`: **sorted** list of active feature names (including
  `"default"` if default features are active). `null` for unreachable.
- `activated_optional_deps`: **sorted** list of optional dependency names
  that were activated by features. `null` for unreachable.
- `resolved_dependencies`: **sorted** list of crate names this crate
  depends on after resolution. `null` for unreachable.
- `depth`: integer or `null` for unreachable.
- `fan_in`, `fan_out`: integers. 0 for unreachable.
- `instability`: float rounded to `output_precision`, or `null` if
  Ca + Ce == 0.
- `active_size`: float rounded to `output_precision`. For unreachable
  crates, use `base_size_bytes` as-is (as a float).
- `layer`: one of `"entry"`, `"leaf"`, `"internal"`, `"unreachable"`.
- `total_exports`: integer count of all available exports, including
  unconditional exports plus conditional exports whose gating feature
  is active. For unreachable crates, count only unconditional exports.

## `dependency_graph`

```json
{
  "total_edges": 40,
  "edges": [
    {"from": "app-server", "to": "auth-module"},
    ...
  ]
}
```

Edges sorted by `(from, to)` ascending.

## `cycles`

```json
{
  "is_acyclic": false,
  "cycle_count": 1,
  "cycles": [
    ["crypto-utils", "tls-provider"]
  ]
}
```

Each inner list sorted alphabetically. Outer list sorted by first element.

## `build_order`

A flat list of crate names in valid build order (dependencies first):

```json
["serde-core", "hash-impl", "query-builder", ...]
```

## `build_checksum`

A SHA-256 hex digest of a **verification string** constructed as:

```
compact_json(build_order) + "\n" + compact_json(feature_digest)
```

Where `feature_digest` is a JSON array of `[crate_name, [sorted_features]]`
pairs for each **reachable** crate, sorted by crate name. Example:

```json
[["app-server",["default"]],["core-lib",["async-support","default",...]],...]
```

Both `compact_json(build_order)` and `compact_json(feature_digest)` use
no spaces and no extra whitespace (JSON separators `,` and `:`).

This verifies that BOTH the build order and feature resolution are
exactly correct. Any deviation in either produces a different checksum.

```json
"build_checksum": "a1b2c3d4..."
```

## `size_analysis`

```json
{
  "total_base_size": 64900,
  "total_active_size": 78595.0,
  "reachable_base_size": 64000,
  "reachable_active_size": 77695.0
}
```

All floats rounded to `output_precision`. Sums are computed over the
active sizes of all crates (total) or only reachable crates (reachable).
Base sizes use the raw `base_size_bytes` integers.

## `findings`

```json
{
  "total": 14,
  "by_severity": {
    "critical": 2,
    "high": 3,
    "medium": 6,
    "low": 2,
    "info": 1
  },
  "items": [
    {
      "type": "dependency_cycle",
      "severity": "critical",
      "module": null,
      "details": {"members": ["crypto-utils", "tls-provider"]}
    },
    ...
  ]
}
```

Items sorted per the findings sort order specification.
