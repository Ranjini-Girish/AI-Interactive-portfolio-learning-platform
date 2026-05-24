# Reactive Dataflow Engine

A spreadsheet-like reactive computation engine that manages cells with values
or formulas, automatically recalculating dependents when inputs change.

## Usage

```bash
node src/main.js
```

Reads input from `data/` and writes results to `output/results.json`.

## Architecture

See `docs/ARCHITECTURE.md` for module structure and `docs/SPEC.md` for the
behavioral specification.
