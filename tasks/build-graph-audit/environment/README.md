# Build Dependency Graph Auditor

Analyze a JavaScript project's module dependency graph and produce
a comprehensive JSON audit report.

## Input Files

- `data/project.json` — project metadata and entry points
- `data/config.json` — thresholds, transform ratios, severity ranks
- `data/modules/*.json` — 19 module definitions with imports, exports,
  re-exports, sizes, and side-effect flags

## Specifications

- `docs/resolution_spec.md` — import resolution and re-export rules
- `docs/metrics_spec.md` — depth, coupling, cycles, build order
- `docs/findings_spec.md` — quality finding types and sort order
- `docs/output_format.md` — JSON output schema

## Starter Code

- `src/main.js` — Node.js entry point (stub)
- `package.json` — npm manifest (no external dependencies needed)

## Output

Write the report to `/app/output/build_graph_report.json`.
