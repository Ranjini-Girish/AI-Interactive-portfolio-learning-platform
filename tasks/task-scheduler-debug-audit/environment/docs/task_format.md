# Task Format

## Input: `/app/data/tasks.json`
```json
{
  "tasks": [
    {
      "id": "string — unique identifier",
      "name": "string — human-readable name",
      "priority": "integer — scheduling priority (lower = higher priority)",
      "duration_ms": "integer — execution time in milliseconds",
      "group": "string — logical grouping",
      "depends_on": ["array of task IDs this task depends on"],
      "resources": "integer — number of resource slots required"
    }
  ]
}
```

## Constraints
- Task IDs are unique alphanumeric strings (may contain underscores).
- `depends_on` references must resolve to existing task IDs.
- The dependency graph must be acyclic (DAG).
- Priority is a positive integer; lower values indicate higher scheduling priority.
- Resources is a positive integer (1-3).
