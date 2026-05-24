# Semantic Version Dependency Resolver

A Go implementation of a package dependency resolver that uses semantic versioning constraints.

## Building

```bash
go build -o /app/build/resolver ./cmd/resolver
```

## Running

```bash
/app/build/resolver
```

Reads input from `/app/data/` and writes output to `/app/output/resolution_report.json`.

## Project Structure

- `cmd/resolver/` - Main entry point
- `internal/semver/` - Semantic version parsing and comparison
- `internal/resolver/` - Dependency resolution algorithm
- `internal/registry/` - Package registry loading
- `internal/output/` - Report generation
- `data/` - Input data and specification
