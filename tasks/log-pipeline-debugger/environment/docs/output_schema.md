# Output JSON Schema

The report at `/app/output/report.json` must have the following structure.
All keys sorted alphabetically at every nesting level. Floating-point values
rounded to 6 decimal places. 2-space indentation. Trailing newline.

```json
{
  "incidents": [
    {
      "service": "<name>",
      "threshold": <float>,
      "type": "<high_error_rate|high_avg_latency>",
      "value": <float>
    }
  ],
  "service_stats": [
    {
      "avg_latency_ms": <float>,
      "error_rate": <float>,
      "errors": <int>,
      "events": <int>,
      "service": "<name>"
    }
  ],
  "summary": {
    "incidents": <int>,
    "services": <int>,
    "time_range_end": <epoch_int>,
    "time_range_start": <epoch_int>,
    "total_events": <int>,
    "unique_traces": <int>
  },
  "trace_summary": [
    {
      "events": <int>,
      "has_error": <bool>,
      "services": <int>,
      "trace_id": "<id>"
    }
  ]
}
```

service_stats sorted by service name (ascending, LC_ALL=C).
incidents sorted by service name then type.
trace_summary sorted by trace_id.
