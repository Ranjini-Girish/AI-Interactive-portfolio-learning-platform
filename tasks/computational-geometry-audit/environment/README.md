# 2D Computational Geometry Auditor

## Container Layout

```
/app/
  geometry_audit.cpp   # starter stub (C++17)
  Makefile             # build rules
  config/
    policy.json        # tolerances, rules, severity config
  scenes/
    scene_01.json … scene_06.json   # geometric scene definitions
  queries/
    query_01.json … query_06.json   # per-scene query specifications
  docs/
    geometry_algorithms.md   # algorithm specs and edge case rules
    output_schema.md         # JSON output format
  output/              # write geometry_audit.json here
```

## Dependencies

- g++ (C++17)
- make
- python3

## Build & Run

```bash
make build
geometry_audit /app
# or write your own solution in Python / any available language
```

## Output

Write `/app/output/geometry_audit.json` following the schema in `docs/output_schema.md`.
