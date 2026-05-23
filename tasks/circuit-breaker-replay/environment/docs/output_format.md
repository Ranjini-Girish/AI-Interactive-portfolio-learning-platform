# Canonical Output Shapes

Every output file is canonical JSON: UTF-8 byte stream, ASCII-only
escaping (`ensure_ascii=True`), two-space indent, lexicographically sorted
object keys at every depth, single trailing newline. Two byte-identical
runs of the simulator on identical inputs must produce byte-identical
output files.

## `final_endpoints.json`

```
{
  "endpoints": [
    {
      "current_failure_threshold_pct": <int 1..100>,
      "current_half_open_max_probes":  <int >= 1>,
      "current_recovery_ticks":        <int >= 0>,
      "current_window_size":           <int >= 1>,
      "id":                            <string>,
      "last_state_change_seq":         <int or null>,
      "probe_failures":                <int >= 0>,
      "probe_successes":               <int >= 0>,
      "probes_used":                   <int >= 0>,
      "state":                         <"CLOSED" | "OPEN" | "HALF_OPEN">,
      "state_transition_count":        <int >= 0>,
      "tick_entered_open":             <int or null>,
      "total_admitted":                <int >= 0>,
      "total_failures":                <int >= 0>,
      "total_short_circuited":         <int >= 0>,
      "total_successes":               <int >= 0>,
      "total_timeouts":                <int >= 0>
    },
    ...
  ]
}
```

The `endpoints` array is sorted by `id` ASCII ascending. The
`current_*` fields report the effective threshold values at trace end
(taking each per-endpoint override when non-null, else `policy.default_*`).
`probes_used`, `probe_successes`, `probe_failures` are zero whenever the
endpoint is in `CLOSED` or `OPEN`. `tick_entered_open` is `null` whenever
the endpoint is not currently `OPEN`. `last_state_change_seq` is the `seq`
of the most recent transition emitted into `state_transitions.transitions`,
or `null` if the endpoint never transitioned.

## `state_transitions.json`

```
{
  "transitions": [
    {
      "endpoint_id":   <string>,
      "from_state":    <"CLOSED" | "OPEN" | "HALF_OPEN">,
      "reason":        <"threshold_breach" | "probe_failure" | "probe_success_quota"
                       | "recovery_timeout" | "manual_open" | "manual_close">,
      "seq":           <int >= 0>,
      "tick":          <int >= 0>,
      "to_state":      <"CLOSED" | "OPEN" | "HALF_OPEN">
    },
    ...
  ]
}
```

`transitions` is sorted by `seq` ascending. Each transition records the
`tick` value of the global tick at the moment the transition occurred
(this is the post-increment tick for a `tick` event, the current tick for
any `request` / `force_*` event). When a single seq triggers transitions
across multiple endpoints (e.g. a `tick` event causing several `OPEN ->
HALF_OPEN` transitions), they are recorded in ASCII-sorted `endpoint_id`
order under the same `seq` value -- but `transitions` itself is still a
flat list, only ordered by `seq` (with intra-seq ordering by
`endpoint_id`).

When `policy.track_state_transitions == false`, this list is empty.

## `request_log.json`

```
{
  "requests": [
    {
      "admission":          <"admitted" | "probe_admitted" | "short_circuited">,
      "endpoint_id":        <string>,
      "outcome":            <"success" | "failure" | "timeout">,
      "seq":                <int >= 0>,
      "state_at_admission": <"CLOSED" | "OPEN" | "HALF_OPEN">
    },
    ...
  ]
}
```

`requests` is sorted by `seq` ascending. Only `request` events that
referenced an existing endpoint produce entries here. A request that was
rejected with `E_ENDPOINT_NOT_FOUND` does NOT appear in `request_log` --
it appears only in `diagnostics`.

## `diagnostics.json`

```
{
  "events": [
    {
      "diagnostics": [
        {
          "code":         <code>,
          "endpoint_id":  <string>,
          "severity":     <"error" | "warning" | "note">
        },
        ...
      ],
      "seq": <int >= 0>
    },
    ...
  ]
}
```

`events` is sorted by `seq` ascending; events with zero diagnostics are
absent. Within each event the `diagnostics` list is sorted by
`(severity_rank, code, endpoint_id)` ascending.

## `summary.json`

```
{
  "endpoints_at_end":               <int >= 0>,
  "events_with_diagnostics":        <int >= 0>,
  "global_tick_at_end":             <int >= 0>,
  "peak_open_endpoints":            <int >= 0>,
  "total_admitted":                 <int >= 0>,
  "total_events":                   <int >= 0>,
  "total_failures":                 <int >= 0>,
  "total_requests":                 <int >= 0>,
  "total_short_circuited":          <int >= 0>,
  "total_state_transitions":        <int >= 0>,
  "total_successes":                <int >= 0>,
  "total_timeouts":                 <int >= 0>,
  "total_transitions_to_closed":    <int >= 0>,
  "total_transitions_to_half_open": <int >= 0>,
  "total_transitions_to_open":      <int >= 0>
}
```

- `endpoints_at_end` is the number of endpoints present at trace end.
- `events_with_diagnostics` is the count of distinct `seq` values that
  produced at least one diagnostic entry.
- `global_tick_at_end` is the value of the global tick at trace end
  (`number of tick events processed`).
- `peak_open_endpoints` is the maximum number of endpoints simultaneously
  in `OPEN` at any point during the trace, observed after each event has
  fully processed.
- `total_admitted`, `total_short_circuited`, and the per-outcome counters
  aggregate across every endpoint that ever existed.
- `total_requests` equals `total_admitted + total_short_circuited`.
- `total_state_transitions` equals the length of
  `state_transitions.transitions` (and is zero when
  `policy.track_state_transitions` is false).
- The three `total_transitions_to_*` counters partition
  `total_state_transitions` into the buckets that match the `to_state` of
  each entry.
