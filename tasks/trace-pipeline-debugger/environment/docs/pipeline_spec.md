# Pipeline Specification

The trace analyzer processes span data through a sequential pipeline of stages. Each stage receives the output of the previous stage and transforms it for the next.

## Stage Order

1. **Parser** — Validates and normalizes raw span data. Spans missing required fields (`span_id`, `trace_id`, `service`, `start_time`, `end_time`) are dropped. Missing optional fields are filled with defaults: `level` defaults to `"info"`, `status` to `"ok"`, `parent_span_id` to `null`.

2. **Filter** — Removes spans below the configured minimum log level. The log levels in ascending severity order are: `debug` (0), `info` (1), `warn` (2), `error` (3). A span passes the filter if its numeric level is greater than or equal to the numeric level of `config.filter.min_level`. Spans from excluded services are also removed.

3. **Correlator** — Groups spans into traces by `trace_id` and builds span trees. See `trace_correlation.md`.

4. **Aggregator** — Computes per-service statistics from the filtered spans. Each service gets independent counters: `count`, `error_count`, `latencies` (array), and `total_duration`. A span is counted as an error if `status === "error"` or `level === "error"`.

5. **Metrics** — Computes derived metrics from the aggregated statistics. See `metrics_reference.md`.

6. **Anomaly** — Detects anomalous spans using z-score analysis. See `anomaly_detection.md`.

7. **Reporter** — Assembles the final report. See `output_schema.md`.

## Latency Computation

Span latency (duration) is computed as `end_time - start_time` in milliseconds. Both timestamps are ISO 8601 strings parsed via `Date.parse()`, which returns epoch milliseconds. The duration is therefore `Date.parse(end_time) - Date.parse(start_time)` with no further scaling.
