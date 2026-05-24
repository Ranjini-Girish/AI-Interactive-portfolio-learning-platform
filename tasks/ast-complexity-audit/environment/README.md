# AST Complexity Audit

Analyze simplified JavaScript AST representations to compute software quality metrics including cyclomatic complexity, cognitive complexity, Halstead metrics, maintainability index, and coupling analysis.

## Structure

- `data/modules/` — JSON files with AST representations of JavaScript modules
- `data/project.json` — Project metadata and module listing
- `config/thresholds.json` — Metric thresholds for findings
- `config/weights.json` — Severity and risk score configuration
- `docs/` — Algorithm specifications
- `src/main.js` — Entry point stub
