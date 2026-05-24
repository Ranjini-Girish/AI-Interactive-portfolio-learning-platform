# DAG Pipeline Event Processor

A Node.js application that processes sensor events through a weighted directed acyclic graph pipeline and generates an audit report.

## Structure

- `src/` — Application source code
- `data/` — Input data files (pipeline definition and events)
- `docs/` — Specification documents
- `output/` — Generated reports (created at runtime)

## Running

```bash
node src/main.js
```

The processor reads from `/app/data/` and writes to `/app/output/pipeline_report.json`.
