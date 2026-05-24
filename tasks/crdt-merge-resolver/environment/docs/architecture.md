# Architecture

## Module Dependency Graph

```
main.js
├── config_loader.js    (loads merge_config.json)
├── replica_loader.js   (loads all replica/*.json files)
├── merge_sort.js       (total order sorting)
├── vector_clock.js     (partial ordering utilities)
├── anomaly_detector.js (causal violation, concurrent write, resurrection, clock regression)
├── lww_resolver.js     (Last-Writer-Wins state resolution)
├── state_hash.js       (SHA-256 state hash computation)
└── report_writer.js    (JSON output with sorted keys)
```

## Data Flow

1. `config_loader` reads `/app/data/config/merge_config.json`
2. `replica_loader` reads all `*.json` files from `/app/data/replicas/`
3. `merge_sort` combines all operations into a total-ordered log
4. `anomaly_detector` scans for causal violations, concurrent writes,
   resurrections, and clock regressions
5. `lww_resolver` determines the final state for each key
6. `state_hash` computes the SHA-256 hash of the active state
7. `report_writer` assembles and writes the merge report

## Key Design Decisions

- Vector clock comparison uses ALL keys from BOTH clocks (missing = 0)
- LWW tie-breaking uses OPPOSITE direction from merge sort ordering
- Resurrections are tracked per transition (a key can be resurrected multiple times)
- Clock regressions are per-replica, checked in log order (not total order)
