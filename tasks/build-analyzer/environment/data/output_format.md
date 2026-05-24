# Output Format

Produce `/app/output/build_report.json` with two-space indent and trailing newline.

## Top-Level Structure
```json
{
  "schema_version": 1,
  "dependency_analysis": { ... },
  "rebuild_analysis": { ... },
  "timing_analysis": { ... },
  "summary": { ... }
}
```

## dependency_analysis
- `total_targets` — integer, total number of targets
- `has_cycles` — boolean
- `cycles` — array of cycle arrays (empty if no cycles)
- `topological_order` — array of target names in build order
- `parallel_levels` — array of level objects, each: `{"level": N, "targets": [...]}`

## rebuild_analysis
- `changed_files` — array of changed file paths (from changes.json)
- `directly_dirty` — array of target names dirty due to own file changes, sorted alphabetically
- `transitively_dirty` — array of target names dirty due to dependency propagation (excluding directly dirty), sorted alphabetically
- `all_dirty` — array of all dirty target names, sorted alphabetically
- `clean` — array of clean target names, sorted alphabetically
- `rebuild_order` — array of dirty targets in topological build order

## timing_analysis
- `sequential_time_ms` — integer, sum of all build times
- `parallel_time_ms` — integer, level-based parallel time
- `critical_path` — array of target names on the critical path (start to end)
- `critical_path_time_ms` — integer, sum of critical path build times
- `speedup_ratio` — float, rounded per config

## summary
- `total_targets` — integer
- `total_levels` — integer (number of parallel levels)
- `dirty_count` — integer
- `clean_count` — integer
- `libraries` — integer (count of library-type targets)
- `executables` — integer (count of executable-type targets)
