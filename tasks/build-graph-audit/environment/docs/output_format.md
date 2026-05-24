# Output Format

The output is a single JSON file at `/app/output/build_graph_report.json`.

## Top-level Keys (in this order)

```json
{
  "schema_version": 1,
  "project_name": "<from project.json>",
  "summary": { ... },
  "modules": [ ... ],
  "dependency_edges": [ ... ],
  "cycles": [ ... ],
  "build_order": [ ... ],
  "size_analysis": { ... },
  "quality_findings": [ ... ]
}
```

## `summary`

```json
{
  "total_modules": <int>,
  "reachable_modules": <int>,
  "unreachable_modules": <int>,
  "entry_points": <int>,
  "total_edges": <int>,
  "cycle_count": <int>,
  "total_findings": <int>,
  "by_severity": {
    "critical": <int>,
    "high": <int>,
    "medium": <int>,
    "low": <int>,
    "info": <int>
  }
}
```

All five severity keys must always be present, even when zero.

## `modules`

Sorted alphabetically by `name`. Each entry:

```json
{
  "name": "<string>",
  "path": "<string>",
  "depth": <int or null>,
  "fan_in": <int>,
  "fan_out": <int>,
  "instability": <float or null>,
  "raw_size_bytes": <int>,
  "minified_bytes": <float>,
  "compressed_bytes": <float>,
  "in_cycle": <boolean>,
  "reachable": <boolean>,
  "layer": "<entry|internal|leaf|unreachable>",
  "used_exports": <int>,
  "total_exports": <int>,
  "used_export_ratio": <float or null>,
  "tree_shake_eligible": <boolean>,
  "potential_savings_bytes": <float>
}
```

## `dependency_edges`

Sorted by `(source, target)` alphabetically. Each entry:

```json
{
  "source": "<module name>",
  "target": "<module name>"
}
```

## `cycles`

Sorted by `cycle_id`. Each entry:

```json
{
  "cycle_id": <int>,
  "members": ["<sorted member names>"],
  "size": <int>
}
```

## `build_order`

A flat array of module name strings in valid topological order,
as specified in `metrics_spec.md`.

## `size_analysis`

```json
{
  "total_raw_bytes": <int>,
  "total_minified_bytes": <float>,
  "total_compressed_bytes": <float>,
  "overall_compression_ratio": <float>,
  "total_potential_savings_bytes": <float>
}
```

`overall_compression_ratio = total_compressed_bytes / total_raw_bytes`.
`total_potential_savings_bytes` is the sum of `potential_savings_bytes`
across all modules.

## `quality_findings`

Sorted as specified in `findings_spec.md`. Each finding uses the
structure defined there.

## Formatting

- Two-space indent.
- Trailing newline after the closing `}`.
- All floating-point values rounded to the number of decimal places
  specified by `config.output_precision`. Trailing zeros after the
  decimal may be omitted (e.g., `0.5` is acceptable for `0.500000`).
- `null` for absent values, not omitted keys.
- Keys within each object follow the order shown above.
