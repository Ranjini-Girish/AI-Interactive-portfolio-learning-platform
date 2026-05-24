# Repository Health Analyzer

Analyzes a Git-like commit graph stored as JSON files and produces a comprehensive health report.

## Data Layout

- `data/commits/` — individual commit objects (one JSON per commit)
- `data/branches.json` — branch name to head commit hash mapping
- `data/tags.json` — tag name to commit hash mapping
- `data/mailmap.json` — email alias normalization rules
- `data/config.json` — analysis parameters

## Source Structure

- `src/main.js` — entry point
- `src/graph.js` — commit DAG traversal
- `src/metrics.js` — metric computation
- `src/authors.js` — author aggregation
- `src/files.js` — file churn and hotspot analysis
- `src/report.js` — report assembly
- `src/utils.js` — shared helpers

## Output

The analyzer writes its report to `output/repo_health_report.json`.
