# Scheduling Algorithm

## 1. Dependency Graph Construction
Build a directed acyclic graph (DAG) where edges go from dependency → dependent.
If task B depends on task A, there is an edge A → B.

## 2. Topological Sort
Use Kahn's algorithm (BFS-based) to produce a topological ordering:
1. Compute in-degree for each node.
2. Initialize a **min-heap** (priority queue) with all zero-in-degree nodes,
   ordered by **(priority ASC, id ASC)** — lower priority number goes first,
   ties broken lexicographically by task ID (earlier ID first).
3. Repeatedly extract the minimum, append to the sorted order, and decrement
   in-degrees of successors. When a successor reaches zero, push it to the heap.

## 3. Scheduling
Tasks execute in topological order. Each task's `start_time` is the **maximum
`end_time`** among all its dependencies (0 for tasks with no dependencies).
There is no overlap or adjustment between stages — a task begins at the exact
tick its last dependency completes. `end_time = start_time + duration_ms`.

## 4. Critical Path
The critical path is the longest path through the DAG measured by cumulative
**duration** (sum of `duration_ms` along the path). Each task on the path
contributes its full duration. Report the total critical path duration and
the ordered list of task IDs on the critical path.

## 5. Group Statistics
For each group, compute:
- `task_count`: number of tasks in that group
- `total_duration`: sum of `duration_ms` for tasks in that group
- `avg_duration`: `total_duration / task_count` (floating-point, rounded to 2 decimals)
- `max_priority`: highest (numerically largest) priority value in that group
- `total_resources`: sum of `resources` for tasks in that group

Groups must be sorted alphabetically by group name in the output.

## 6. Dependency Depth
For each task, compute `depth` = the length of the longest path from any root
node (a node with no dependencies) to that task. Root nodes have depth 0.
For tasks with multiple dependencies, depth = max(dependency depths) + 1.

## 7. Integrity Hash
Compute a chained SHA-256 hash over the schedule entries (in topological/execution order):
1. Start with an empty string as the previous hash.
2. For each scheduled task, form a line: `task_id|start_time|end_time|depth|resources`
3. Concatenate: `previous_hash + line`
4. Compute SHA-256 hex digest of the concatenation. This becomes the new previous hash.
5. The final hash after processing all tasks is the `integrity_hash`.

## 8. Summary Metrics
- `total_tasks`: count of all tasks
- `total_duration`: sum of all task durations (sequential time)
- `makespan`: maximum end_time across all scheduled tasks (parallel time)
- `parallelism_ratio`: `total_duration / makespan`, rounded to 2 decimal places
- `total_resources`: sum of `resources` across all tasks
