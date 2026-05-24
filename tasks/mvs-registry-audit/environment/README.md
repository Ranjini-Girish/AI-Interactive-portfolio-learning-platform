# Dependency Graph Audit Tool

A Go program that resolves package dependencies using Minimal Version Selection, analyzes the dependency graph, and produces a comprehensive audit report.

## Project Structure

- `cmd/depaudit/main.go` — entry point
- `internal/resolver/` — MVS resolution engine
- `internal/graph/` — graph algorithms (cycles, topological sort)
- `internal/metrics/` — coupling and vulnerability metrics
- `internal/report/` — JSON report generation
- `data/` — input registry and advisory data
- `config/` — resolution policy
- `docs/` — algorithm specifications

## Build & Run

```bash
go build -o /app/depaudit ./cmd/depaudit/
./depaudit
```

Output: `/app/output/dep_audit.json`
