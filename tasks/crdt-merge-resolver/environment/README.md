# CRDT Merge Resolver

A Node.js tool that merges CRDT operation logs from distributed replica nodes into a causally consistent total order and produces a comprehensive merge report.

## Architecture

```
src/main.js           - Entry point, orchestrates the merge pipeline
lib/vector_clock.js   - Vector clock comparison (partial ordering)
lib/anomaly_detector.js - Causal anomaly detection
lib/lww_resolver.js   - Last-Writer-Wins state resolution
lib/state_hash.js     - SHA-256 state hash computation
```

## Data Layout

```
data/replicas/        - One JSON file per replica node
data/config/          - Merge configuration
docs/                 - Specification documents
```

## Running

```bash
node src/main.js
```

Output is written to `/app/output/merge_report.json`.
