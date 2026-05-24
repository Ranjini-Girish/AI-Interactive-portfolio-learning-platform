# Output Schema — `/app/output/report.json`

```json
{
  "schedule": [
    {
      "task_id": "string",
      "name": "string",
      "group": "string",
      "priority": integer,
      "start_time": integer (ms),
      "end_time": integer (ms),
      "duration_ms": integer,
      "depth": integer,
      "dependencies": ["array of task IDs"],
      "resources": integer
    }
  ],
  "critical_path": {
    "total_duration": integer (ms),
    "tasks": ["ordered list of task IDs on the critical path"]
  },
  "group_stats": {
    "<group_name>": {
      "task_count": integer,
      "total_duration": integer,
      "avg_duration": float (2 decimal places),
      "max_priority": integer,
      "total_resources": integer
    }
  },
  "summary": {
    "total_tasks": integer,
    "total_duration": integer (sum of all task durations),
    "makespan": integer (end_time of last task),
    "parallelism_ratio": float (total_duration / makespan, 2 decimal places),
    "total_resources": integer (sum of all task resources)
  },
  "integrity_hash": "string (64-char hex SHA-256)"
}
```

- `schedule` is ordered by execution order (topological sort with priority).
- All times are in milliseconds.
- Keys in `group_stats` are sorted alphabetically.
- JSON uses 2-space indentation and trailing newline.
