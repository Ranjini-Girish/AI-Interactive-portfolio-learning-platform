# Output Format

Five files in `/app/output/`. Every file is canonical JSON: UTF-8,
ASCII-only escaping (`ensure_ascii=True`), two-space indent, object
keys lex-sorted at every depth, single trailing newline. Integer values
stay integers (do not emit them as JSON numbers with a decimal point);
booleans stay booleans; the empty list is `[]` not `null`.

## `sampling_decisions.json`

```
{
  "decisions": [
    {
      "decision":       "keep" | "drop",
      "matched_policy": <policy name> | null,
      "reason":         "cycle_detected" | "multi_root" |
                        "incomplete_trace" | "orphan_span" |
                        "policy_match" | "no_policy_matched",
      "trace_id":       <16-hex string>
    },
    ...
  ]
}
```

Sorted ASCII ascending by `trace_id`. Includes every distinct `trace_id`
in `spans.json` exactly once.

`matched_policy` is the `name` of the policy that produced the decision
when `reason == "policy_match"`, otherwise `null`. Probabilistic
policies that drop a trace still set `matched_policy` to their name --
the policy MATCHED, the per-trace bucket simply landed in the
drop band.

## `policy_stats.json`

```
{
  "policies": [
    {
      "dropped_count": <int>,
      "kept_count":    <int>,
      "matched_count": <int>,
      "name":          <policy name>,
      "type":          "status_match" | "latency" | "attribute" |
                       "service" | "probabilistic"
    },
    ...
  ]
}
```

Sorted ASCII ascending by `name`. Includes every policy declared in
`policies.json`, even ones that matched zero traces (all three counts
are then `0`).

Invariant: `matched_count == kept_count + dropped_count`.

## `service_stats.json`

```
{
  "services": [
    {
      "dropped_traces":        <int>,
      "error_spans":           <int>,
      "kept_traces":           <int>,
      "max_trace_duration_ms": <int>,
      "service":               <service name>,
      "span_count":            <int>,
      "timeout_spans":         <int>,
      "trace_count":           <int>
    },
    ...
  ]
}
```

Sorted ASCII ascending by `service`. Includes every service that
appears in at least one span.

- `span_count` is the number of spans whose `service` matches.
- `error_spans` is the number of spans with `status == "error"`.
- `timeout_spans` is the number of spans with `status == "timeout"`.
- `trace_count` is the number of DISTINCT `trace_id`s that have at
  least one span of this service.
- `kept_traces` / `dropped_traces` partition `trace_count` by the
  final per-trace decision. A trace with multiple spans of the same
  service counts ONCE per (service, trace) pair.
- `max_trace_duration_ms` is the maximum of
  `trace_total_duration_ms = max(start_unix_ms + duration_ms) -
   min(start_unix_ms)` across traces that touch this service. Zero
  when only one span (max == min, duration_ms == 0) yields zero.

Invariant: `trace_count == kept_traces + dropped_traces`.

## `trace_diagnostics.json`

```
{
  "diagnostics": [
    {
      "code":          <one of D_*>,
      "evidence":      { ... per-code keys, see diagnostics.md ... },
      "severity":      "error" | "warn" | "info",
      "severity_rank": <int>,
      "span_id":       <8-hex string> | null,
      "trace_id":      <16-hex string>
    },
    ...
  ]
}
```

Sorted by `(severity_rank ascending, trace_id ascending, code ASCII
ascending, span_id ascending with null first)`. Diagnostic codes are
restricted to the closed five-code set in `diagnostics.md`.

## `summary.json`

```
{
  "anomaly_counts": {
    "D_CYCLE_DETECTED":   <int>,
    "D_FUTURE_TIMESTAMP": <int>,
    "D_INCOMPLETE_TRACE": <int>,
    "D_MULTI_ROOT":       <int>,
    "D_ORPHAN_SPAN":      <int>
  },
  "hottest_service":  <service name> | null,
  "kept_traces":      <int>,
  "spans_total":      <int>,
  "traces_dropped":   <int>,
  "traces_total":     <int>
}
```

`anomaly_counts.<CODE>` is the number of entries in
`trace_diagnostics.diagnostics[]` whose `code` matches; every legal code
appears in the object with `0` when none were emitted (no sparse keys).
`hottest_service` is the service with the maximum `span_count` from
`service_stats.json`, with ASCII-ascending `service` as the tiebreaker;
it is `null` only when `spans_total == 0`. Invariants:
`kept_traces + traces_dropped == traces_total` and `traces_total` is the
number of distinct `trace_id`s in the input.
