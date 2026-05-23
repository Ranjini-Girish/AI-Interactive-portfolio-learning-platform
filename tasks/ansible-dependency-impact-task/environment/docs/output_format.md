# Output Formats

All JSON output files must be written in UTF-8 format, with a 2-space indentation and exactly one trailing newline character. Keys at all levels should be sorted if required by the test assertions (canonical JSON).

## 1. /app/output/playbook_drift.json
```json
{
  "schema_version": 1,
  "baseline_sha256": "string",
  "current_sha256": "string",
  "summary": {
    "added_tasks_count": 0,
    "removed_tasks_count": 0,
    "modified_tasks_count": 0
  },
  "added_tasks": [
    {
      "task_name": "string",
      "play_name": "string",
      "module": "string",
      "parameters": {}
    }
  ],
  "removed_tasks": [
    {
      "task_name": "string",
      "play_name": "string",
      "module": "string",
      "parameters": {}
    }
  ],
  "modified_tasks": [
    {
      "task_name": "string",
      "play_name": "string",
      "changed_parameters": {
        "parameter_key": {
          "old_value": null,
          "new_value": null
        }
      }
    }
  ]
}
```

## 2. /app/output/dependency_impact.json
```json
{
  "resolver_summary": {
    "selected_total": 0,
    "missing": [],
    "conflicts": [],
    "cycle_group_count": 0
  },
  "seed_modules": [
    {
      "task_ref": "string",
      "module": "string",
      "version": "string"
    }
  ],
  "impacted_modules": [
    {
      "name": "string",
      "version": "string",
      "triggered_by": []
    }
  ],
  "cycles": [
    ["string", "string"]
  ],
  "build_order": [
    ["string", "string"]
  ]
}
```

## 3. /app/output/remediation_plan.json
```json
{
  "steps": [
    {
      "step": 1,
      "modules": [],
      "triggered_by": []
    }
  ]
}
```
