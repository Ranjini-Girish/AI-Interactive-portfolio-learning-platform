# Quality Findings Specification

## Finding Structure

Every finding has these keys:

```json
{
  "finding_type": "<string>",
  "severity": "<string>",
  "severity_rank": "<int from config.severity_ranks>",
  "module": "<module name or null>",
  "evidence": { ... }
}
```

## Finding Types

### `oversized_module` — severity `medium`
Emitted for each module whose `size_bytes` exceeds
`config.thresholds.oversized_module_bytes`.

Evidence: `{"size_bytes": <int>, "threshold": <int>}`.

### `high_instability` — severity `low`
Emitted for each module whose instability strictly exceeds
`config.thresholds.max_instability`. Modules with `null`
instability are excluded.

Evidence: `{"instability": <float>, "threshold": <float>}`.

### `excessive_fan_out` — severity `medium`
Emitted for each module whose fan-out (Ce) strictly exceeds
`config.thresholds.max_fan_out`.

Evidence: `{"fan_out": <int>, "threshold": <int>}`.

### `deep_module` — severity `high`
Emitted for each module whose depth strictly exceeds
`config.thresholds.max_depth`. Modules with `null` depth
are excluded.

Evidence: `{"depth": <int>, "threshold": <int>}`.

### `dependency_cycle` — severity `critical`
Emitted once per detected cycle (SCC with ≥ 2 members).
The `module` field is `null` (the finding applies to the
cycle, not a single module).

Evidence: `{"cycle_id": <int>, "members": [<sorted names>],
"size": <int>}`.

### `unreachable_module` — severity `info`
Emitted for each module not reachable from any entry point.

Evidence: `{"module_path": "<path from module definition>"}`.

## Sort Order

Findings are sorted by:
1. `severity_rank` descending (critical first)
2. `finding_type` ascending (alphabetical)
3. `module` ascending — with `null` treated as the empty string `""`
   (so `null` sorts before any module name)
