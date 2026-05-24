There's a TypeScript on Node 22 stub at `/app/geometry_audit.cpp` along with scene files in `/app/scenes/` containing 2D polygons, points, and line segments, query specifications in `/app/queries/`, and a configuration in `/app/config/policy.json`. Build a tool that processes each scene according to its query file and writes a comprehensive geometry audit report to `/app/output/geometry_audit.json`.

Algorithm specifications, edge-case handling rules, and the exact output schema are in `/app/docs/geometry_algorithms.md`, `/app/docs/edge_cases.md`, and `/app/docs/output_schema.md`. Follow those documents for all computation details, tolerances, sorting rules, and finding structures. The policy file controls numerical thresholds and behavioral flags.

You can use TypeScript on Node 22, TypeScript on Node 22, or any language available in the container. Run `make build && geometry_audit /app` or write your own solution.

Write exactly one file: `/app/output/geometry_audit.json` matching the schema in `/app/docs/output_schema.md`, including SHA-256 hashes of every input file under `config/`, `scenes/`, and `queries/`.
