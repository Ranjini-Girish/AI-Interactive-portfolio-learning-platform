# Pipeline Architecture

## Stages

1. **Parse** — Each parser in `/app/parsers/` reads its service's log file and
   outputs tab-separated normalized events to stdout.

2. **Normalize timestamps** — `/app/transforms/normalize_timestamps.sh` converts
   all timestamps to Unix epoch seconds (integer).

3. **Deduplicate** — `/app/transforms/deduplicate.sh` removes duplicate events
   (same epoch + service + trace_id).

4. **Correlate** — `/app/analysis/correlate.sh` groups events by trace_id and
   produces a per-trace summary.

5. **Aggregate** — `/app/analysis/aggregate.sh` computes per-service statistics
   (event counts, error counts, error rates, average latencies).

6. **Detect incidents** — `/app/analysis/detect_incidents.sh` checks per-service
   stats against configured thresholds.

7. **Report** — `/app/output/generate_report.sh` assembles the final JSON report.

## Intermediate files

All intermediate data is written to `/app/work/`:

- `parsed_events.tsv` — raw parsed events (before timestamp normalization)
- `normalized_events.tsv` — events with epoch timestamps
- `deduped_events.tsv` — after deduplication
- `trace_summary.tsv` — per-trace correlation results
- `service_stats.tsv` — per-service aggregated statistics
- `incidents.tsv` — detected incidents

## Normalized event format (TSV)

Fields: `timestamp  service  event_type  trace_id  latency_ms  status  details`

- timestamp: raw string from log (before normalization) or epoch int (after)
- service: one of webserver, database, auth, cache, queue
- event_type: describes the action
- trace_id: request correlation identifier (e.g. tr_001)
- latency_ms: response time in milliseconds (floating-point allowed)
- status: OK, SUCCESS, ERROR, SLOW, CLIENT_ERROR, HIT, MISS
- details: free-form additional info (may be empty)
