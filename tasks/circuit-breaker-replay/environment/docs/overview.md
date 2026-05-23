# Circuit Breaker Replay Overview

The simulator models a flat collection of independent, stringly-named
endpoints. Each endpoint has its own circuit-breaker state machine over the
three states `CLOSED`, `OPEN`, and `HALF_OPEN`. There is one shared global
integer tick that starts at `0` and advances by exactly `1` on every `tick`
event. Each endpoint also carries its own sliding window of recent request
outcomes, its own thresholds (taken from the per-endpoint overrides if
non-null, otherwise from the matching `policy.default_*`), and its own
`tick_entered_open` timestamp once it transitions to `OPEN`.

The initial state is `endpoints.json`. Every endpoint listed there starts in
`CLOSED` with an empty window, `probes_used = 0`, no recorded transitions,
and zeroed counters. New endpoints can be added at any seq via
`add_endpoint`; doing so for an `id` that already exists is rejected with a
diagnostic and changes nothing. Endpoints can also be removed (`remove_endpoint`)
or reconfigured (`config_update`) over the course of the trace.

`events.json` is a strictly ascending list of operations (`seq` 0..N-1, dense)
that drive the simulator. Events are processed one at a time in `seq` order.
After every event the global invariants must hold:

- every endpoint is in exactly one of `CLOSED`, `OPEN`, `HALF_OPEN`,
- `probes_used`, `probe_successes`, and `probe_failures` are zero whenever
  the endpoint is in `CLOSED` or `OPEN`,
- `tick_entered_open` is `null` when the endpoint is not currently in `OPEN`,
- `state_transition_count` equals the number of distinct transitions emitted
  for that endpoint into `state_transitions.transitions`,
- the window only contains outcomes from `request` events processed while the
  endpoint was in `CLOSED`. Probe outcomes from `HALF_OPEN` and short-circuited
  requests in `OPEN` are not added to the window.

Diagnostic-emitting failures (e.g. a `request` whose `endpoint_id` does not
exist) do not change endpoint state -- the simulator emits the documented
diagnostic for that event into the relevant per-event `diagnostics.events`
entry and moves on.

## Output bundle

The simulator produces five JSON files under `/app/output/`:

- `final_endpoints.json` -- the endpoint table at trace end, sorted by `id`,
- `state_transitions.json` -- chronological state-machine transitions,
- `request_log.json` -- chronological per-request admission decisions,
- `diagnostics.json` -- per-event diagnostic codes,
- `summary.json` -- aggregate counters.

See `output_format.md` for every field. See `state_machine.md` for the state
machine rules and `events.md` for per-op semantics. The closed diagnostic-code
catalogue is in `diagnostics.md`.
