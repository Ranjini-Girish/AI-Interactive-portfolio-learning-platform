# Output Format Specification

The output file must be written to `/app/output/workspace_audit.json`.

## JSON Formatting

- 2-space indentation
- All object keys sorted alphabetically at every nesting level
- Trailing newline after the closing brace
- No trailing commas
- Floating-point numbers rounded to exactly 4 decimal places (e.g., `1.5000`, not `1.5`)
- Use JSON number type for all numeric values (not strings)

## Schema

```json
{
  "dependency_graph": {
    "<workspace_pkg_dir>": {
      "<dependency_name>": {
        "depth": <integer>,
        "version": "<resolved_version_string>"
      }
    }
  },
  "findings": [
    {
      "category": "<string>",
      "dependency": "<string>",
      "detail": "<string>",
      "finding_id": "<string>",
      "package": "<string>",
      "risk_score": <number>,
      "severity": "<string>"
    }
  ],
  "hoisting": {
    "conflicts": ["<string>"],
    "hoistable": ["<string>"]
  },
  "metadata": {
    "evaluation_date": "<YYYY-MM-DD>",
    "scope": "dependencies",
    "source_hash": "<64-char hex sha256>",
    "workspace_packages": ["<string>"]
  },
  "summary": {
    "aggregate_risk_score": <number>,
    "avg_depth": <number>,
    "conflict_count": <integer>,
    "hoistable_count": <integer>,
    "total_dependencies": <integer>,
    "total_findings": <integer>
  }
}
```

## Key Constraints

- `finding_id` format: `"F-001"`, `"F-002"`, ... (zero-padded to 3 digits)
- `workspace_packages` in metadata: sorted alphabetically by directory name
- `findings` array: ordered by generation sequence (see ALGORITHM.md)
- `hoisting.conflicts` and `hoisting.hoistable`: sorted alphabetically
- `dependency_graph` keys: sorted alphabetically at both package and dependency levels
