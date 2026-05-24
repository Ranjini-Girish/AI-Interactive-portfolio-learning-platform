# Log Analysis Pipeline

A Bash pipeline that ingests logs from five microservices, normalizes
and correlates them, detects incidents, and produces a JSON report.

## Quick Start

```bash
cd /app
bash pipeline.sh
cat output/report.json
```

## Architecture

See `docs/architecture.md` for the full pipeline description.
