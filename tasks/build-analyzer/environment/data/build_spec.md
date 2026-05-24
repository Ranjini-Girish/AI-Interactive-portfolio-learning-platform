# Build System Specification

## Target Definitions
Each `.json` file in `/app/data/targets/` defines a build target with:
- `name` — unique identifier
- `type` — `library` or `executable`
- `sources` — list of source file paths owned by this target
- `headers` — list of header file paths owned by this target
- `depends_on` — list of target names this target depends on (must be built first)
- `build_time_ms` — wall-clock time to build this target in milliseconds

## Dependency Graph Analysis
1. Parse all target definitions and construct the dependency graph.
2. Detect cycles using DFS. If a cycle exists, report it as a list of target names forming the cycle (starting and ending with the same name). A self-dependency counts as a cycle.
3. Compute a topological ordering of all targets. Within equal depth, sort alphabetically by name ascending.

## Parallel Level Assignment
Assign each target a parallel level:
- A target with no dependencies is at level 0.
- A target whose dependencies are all at levels < N is at level N, where N = max(dependency levels) + 1.
- Targets at the same level can be built simultaneously.
- Within each level, targets are sorted alphabetically by name ascending.

## Timing Analysis
- `sequential_time_ms` — sum of all targets' build times (full serial build).
- `parallel_time_ms` — sum over all levels of the max build time within each level.
- `critical_path` — the sequence of targets forming the longest chain by total build time. Trace backwards from the target with the highest cumulative time: at each step, follow the dependency with the highest cumulative time. Break ties alphabetically ascending.
- `critical_path_time_ms` — sum of build times of targets on the critical path.
- `speedup_ratio` — `sequential_time_ms / parallel_time_ms`, rounded to N decimal places per config.
