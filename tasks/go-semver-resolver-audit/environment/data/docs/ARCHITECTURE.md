# Architecture

## Overview

The resolver reads input data (registry, requests, config) and produces a resolution report by applying the BFS resolution algorithm specified in SPEC.md.

## Data Flow

```
registry.json ─┐
               ├──> Resolver Engine ──> resolution_report.json
requests.json ─┤
               │
config.json ───┘
```

## Module Structure

### cmd/resolver
Entry point. Loads data, runs resolution for each request, writes output.

### internal/semver
- Parsing version strings into structured types
- Comparing versions for precedence
- Parsing constraint strings (^, ~, >=, <, ranges, OR groups)
- Matching a version against a constraint

### internal/resolver
- BFS resolution algorithm
- Constraint accumulation and intersection
- Conflict detection
- Depth and requester tracking

### internal/registry
- Loading and indexing the package registry
- Looking up available versions for a package
- Looking up dependencies for a specific version

### internal/output
- Generating the JSON report structure
- Sorting and formatting output

## Key Design Decisions

1. Versions are stored as structured types (not strings) for correct comparison.
2. Constraints are parsed into an AST of comparators joined by AND/OR.
3. The resolution queue processes packages level by level (BFS) with alphabetical ordering within each level.
4. Pre-release filtering is applied at constraint matching time, not at version parsing time.
