# Streaming Statistics Pipeline Auditor

## Container Layout

```
/app/
  pipeline_audit.cpp   # starter stub (C++17)
  Makefile             # build rules
  config/
    pipeline.json      # global configuration, thresholds, severity mappings
  streams/
    stream_01.json … stream_12.json   # sensor data streams
  pipelines/
    pipeline_01.json … pipeline_12.json   # per-stream computation specs
  docs/
    algorithms.md      # statistical algorithm specifications
    output_schema.md   # JSON output format
    edge_cases.md      # edge-case handling rules
  output/              # write pipeline_audit.json here
```

## Dependencies

- g++ (C++17)
- make
- python3

## Build & Run

```bash
make build
pipeline_audit /app
# or write your own solution in Python / any available language
```

## Output

Write `/app/output/pipeline_audit.json` following the schema in `docs/output_schema.md`.
