# Output Schema

The report is written to `/app/output/trace_report.json` with 2-space indentation and a trailing newline.

## Top-Level Structure

```json
{
  "metadata": { ... },
  "results": { ... },
  "integrity": { ... }
}
```

## metadata

- **generated_at**: ISO 8601 timestamp of report generation.
- **config_hash**: SHA-256 hex digest of the JSON-serialized config.
- **span_files_processed**: Number of `.jsonl` files read.
- **total_spans_parsed**: Total number of spans loaded (before filtering).

## results

### trace_summary

- **total_traces**: Number of valid traces constructed.
- **complete_traces**: Traces with a non-null root span.
- **incomplete_traces**: Traces with a null root span.
- **avg_spans_per_trace**: Mean number of spans per trace, rounded to `precision` decimals.

### service_stats

Object keyed by service name. Each value contains:
- `span_count`, `error_count`, `error_rate`
- `latency`: `{ mean, min, max, p50, p90, p95, p99 }`

### dependency_graph

Array of edges sorted by `(source, target)` alphabetically. Each edge:
- `source`: Calling service name.
- `target`: Called service name.
- `call_count`: Number of parent-child span pairs crossing this service boundary.

Only inter-service edges are included (same-service parent-child pairs are excluded).

### anomalies

Array of anomaly records sorted by z_score descending.

## integrity

- **results_hash**: `"sha256:"` followed by the SHA-256 hex digest of `JSON.stringify(report.results)`. This hash covers ONLY the `results` object, NOT `metadata` or `integrity`. This ensures the hash is deterministic across runs (since `metadata.generated_at` changes).
