# Architecture

## Pipeline Stages

1. **Load** (`src/loader.js`) — reads all JSON data files from `/app/data/`
2. **Validate** (`src/validator.js`) — validates product IDs against format rules
3. **Merge** (`src/merger.js`) — joins inventory + transactions by normalizing
   product IDs (removing hyphens) so that inventory IDs (e.g. `PROD-001`)
   match transaction IDs (e.g. `PROD001`)
4. **Calculate** (`src/calculator.js`) — computes per-warehouse values,
   transaction totals by category, median transaction amount
5. **Detect** (`src/detector.js`) — finds anomalies: low stock, missing
   suppliers, price discrepancies
6. **Aggregate** (`src/aggregator.js`) — groups and summarizes metrics
7. **Format** (`src/formatter.js`) — prepares numbers for output (rounding)
8. **Report** (`src/reporter.js`) — assembles and writes the final JSON

## Configuration

`src/config.js` exports thresholds and settings used throughout the pipeline.
Per-warehouse overrides are computed in the pipeline.
