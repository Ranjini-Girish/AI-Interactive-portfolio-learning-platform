# Task Scheduler

A dependency-aware task scheduler. Reads task definitions, builds a DAG,
performs topological sort, and produces a JSON execution report.

```bash
cd /app && cargo run --release
cat /app/output/report.json
```
