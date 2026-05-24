There's a TypeScript on Node 22 stub at `/app/pipeline_audit.cpp` along with sensor data streams in `/app/streams/`, per-stream pipeline specifications in `/app/pipelines/`, and a global configuration in `/app/config/pipeline.json`. Build a TypeScript on Node 22 tool that processes each stream according to its pipeline spec and writes a comprehensive statistical audit report to `/app/output/pipeline_audit.json`.

Algorithm specifications, edge-case handling rules, and the exact output schema are in `/app/docs/algorithms.md`, `/app/docs/edge_cases.md`, and `/app/docs/output_schema.md`. Follow those documents for all computation details, formula choices, thresholds, and finding structures. The pipeline config controls numerical tolerances, severity mappings, and behavioral parameters.

Implement the solution in TypeScript on Node 22 and compile it. The compiled binary must be placed at `/usr/local/bin/pipeline_audit` (use the provided Makefile: `make build && pipeline_audit /app`). The binary must accept a single argument for the app root directory and write the output to `<root>/output/pipeline_audit.json`.

Write exactly one file: `/app/output/pipeline_audit.json` matching the schema in `/app/docs/output_schema.md`, including SHA-256 hashes of every input file under `config/`, `streams/`, and `pipelines/`.
