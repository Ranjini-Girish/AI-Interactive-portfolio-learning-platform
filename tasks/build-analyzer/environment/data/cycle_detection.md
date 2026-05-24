# Cycle Detection

## Algorithm
Use depth-first search to detect cycles in the dependency graph.

## Reporting
- `has_cycles` — boolean, true if any cycle exists.
- `cycles` — array of cycle paths. Each cycle is an array of target names starting and ending with the same target, representing the cycle. Example: `["A", "B", "C", "A"]` means A depends on B, B depends on C, C depends on A.
- If cycles exist, the topological order should contain ONLY targets that are not part of any cycle.
- Cycle paths are sorted alphabetically by their first element. If two cycles share the same starting element, sort by the second element, and so on.

## Self-Dependencies
A target that lists itself in its own `depends_on` is a trivial cycle: `["A", "A"]`.
