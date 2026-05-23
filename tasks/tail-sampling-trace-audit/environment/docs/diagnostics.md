# Diagnostic Codes

`trace_diagnostics.json` carries every diagnostic the simulator
emitted across the run. Exactly FIVE codes are legal -- any other code
in the output file is a verifier failure.

| Code                  | Severity | Fires per | Span ID  |
|-----------------------|----------|-----------|----------|
| `D_CYCLE_DETECTED`    | error    | trace     | `null`   |
| `D_MULTI_ROOT`        | warn     | trace     | `null`   |
| `D_INCOMPLETE_TRACE`  | info     | trace     | `null`   |
| `D_ORPHAN_SPAN`       | warn     | each orphan | the orphan's `span_id` |
| `D_FUTURE_TIMESTAMP`  | warn     | each offending span | the offending `span_id` |

`severity` strings are `"error"`, `"warn"`, and `"info"`. The integer
`severity_rank` MUST be looked up from `config.severity_ranks` at run
time (do not hardcode the integers); the visible dataset uses
`{"error": 0, "warn": 1, "info": 2}` but other datasets may map the
same severity strings to different integers.

## Evidence keys (closed)

```
D_CYCLE_DETECTED:
  cycle_span_ids: [ <span_id>, ... ]   // sorted ASCII ascending

D_MULTI_ROOT:
  root_span_ids:  [ <span_id>, ... ]   // sorted ASCII ascending

D_INCOMPLETE_TRACE:
  actual_spans:   <int>
  min_required:   <int>

D_ORPHAN_SPAN:
  missing_parent_span_id: <span_id>    // the dangling parent_span_id

D_FUTURE_TIMESTAMP:
  now_unix_ms:    <int>                // copy of config.now_unix_ms
  skew_ms:        <int>                // span.start_unix_ms - config.now_unix_ms (signed)
  start_unix_ms:  <int>                // copy of the span's start_unix_ms
```

Evidence keys not listed above are FORBIDDEN -- the byte-for-byte
comparison rejects any extra or missing field.

## Sort order

`trace_diagnostics.diagnostics[]` is sorted by:

1. `severity_rank` ascending (so the highest-severity entries appear
   first when error_rank=0 < warn_rank=1 < info_rank=2 as in the
   visible dataset).
2. `trace_id` ASCII ascending.
3. `code` ASCII ascending.
4. `span_id` ASCII ascending. `null` sorts BEFORE every string (so the
   per-trace entries appear before the per-span entries for the same
   trace_id + code).

## D_FUTURE_TIMESTAMP is decision-neutral

`D_FUTURE_TIMESTAMP` NEVER overrides a sampling decision -- it is a
metadata-only diagnostic. Even when every span of a trace is
future-timestamped, the trace's final `decision` is still whatever the
policy chain (or `no_policy_matched`) produced. The other four codes
ride along the failing validation check and therefore appear together
with a non-policy_match `reason`.
