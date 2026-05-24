# Parallel Execution Rules

## Level-Based Scheduling
The parallel time estimate uses a conservative level-based scheduling model:
- All targets at level 0 start simultaneously at time 0.
- All targets at level N start when ALL targets at level N-1 have completed.
- The time for a level is the maximum build_time_ms among all targets at that level.
- Total parallel time is the sum of per-level times.

This is more conservative than true unlimited-parallelism scheduling (where a target starts as soon as its own dependencies finish), but it produces deterministic, easily verifiable results.

## Critical Path
The critical path represents the longest chain through the dependency graph measured by cumulative build time. It determines the theoretical minimum build time with unlimited parallelism.

To compute the critical path:
1. For each target, compute `cumulative_time = build_time_ms + max(cumulative_time of each dependency)`. A target with no dependencies has `cumulative_time = build_time_ms`.
2. The critical path ends at the target with the highest cumulative_time. Break ties alphabetically ascending.
3. Trace backwards: at each step, follow the dependency with the highest cumulative_time. Break ties alphabetically ascending.
4. Reverse the traced path to get start-to-end order.

## Speedup Ratio
`speedup_ratio = sequential_time_ms / parallel_time_ms`, rounded to the number of decimal places specified in config.json (`speedup_decimal_places`).
