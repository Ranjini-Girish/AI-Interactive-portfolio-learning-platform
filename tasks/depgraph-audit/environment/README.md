# Dependency Graph Auditor

## Container Layout

```
/app/
  cmd/depaudit/main.go     # entry point stub
  internal/audit/audit.go  # audit logic stub
  go.mod                   # Go module file
  config/
    audit.json             # audit configuration, license matrix, severity mappings
  data/
    registry/
      module_01.json … module_12.json   # module definitions with versions and deps
    queries/
      query_01.json … query_08.json     # resolution queries
    vulnerabilities.json                # known vulnerability database
  docs/
    algorithms.md          # resolution and analysis algorithm specs
    output_schema.md       # JSON output format
    edge_cases.md          # edge-case handling rules
  output/                  # write dependency_audit.json here
```

## Dependencies

- Go 1.23+ (available in container)
- python3 (available in container)

## Build & Run

```bash
cd /app && go build -o /usr/local/bin/depaudit ./cmd/depaudit && depaudit /app
# or write your own solution in Python / any available language
```

## Output

Write `/app/output/dependency_audit.json` following the schema in `docs/output_schema.md`.
