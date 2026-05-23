# Event Semantics

Every event in `events.json` carries `seq` (strictly ascending, dense from
zero) and `op`, plus an op-specific payload. Events are processed one at a
time in `seq` order. The full payload schema lives in
`/app/schemas/events_input.schema.json`; this document explains the runtime
semantics for each `op`.

## `request`

Fields: `endpoint_id` (string, required), `outcome` (one of `"success"`,
`"failure"`, `"timeout"`).

If `endpoint_id` is not currently present, emit `E_ENDPOINT_NOT_FOUND` for
that seq with `endpoint_id == endpoint_id` and stop. No request_log entry
is appended.

Otherwise, the dispatcher records exactly one row in `request_log.requests`
with `seq`, `endpoint_id`, `outcome` (the supplied value), the
`state_at_admission` (the endpoint's state immediately before admission
processing), and the `admission` decision. The admission decision and
state-machine effects depend on `state_at_admission`:

- `CLOSED`: `admission == "admitted"`. The outcome is appended to the
  sliding window (after `time_based` pruning if the strategy is time-based).
  If the post-insert window has both `requests_in_window >=
  policy.min_window_observations` AND `floor(failure_count_in_window * 100 /
  requests_in_window) >= effective failure_threshold_pct`, the endpoint
  transitions `CLOSED -> OPEN` (`reason == "threshold_breach"`).
- `OPEN`: `admission == "short_circuited"`. No window update, no probe
  update, no state transition (only a later `tick` event can move the
  endpoint to `HALF_OPEN`).
- `HALF_OPEN`: `admission == "probe_admitted"`. The outcome is NOT added to
  the window; instead `probes_used` increments and either `probe_successes`
  or `probe_failures` increments. Then the verdict in `state_machine.md`
  applies (`probe_failure` -> `OPEN` immediately on the very first failing
  probe, `probe_success_quota` -> `CLOSED` once `probe_successes >=
  effective half_open_max_probes`).

In all three admitted/short-circuited cases the endpoint's per-state running
counters are updated:

- `total_admitted` is incremented for `CLOSED` and `HALF_OPEN` admissions,
- `total_short_circuited` is incremented for `OPEN` admissions,
- exactly one of `total_successes`, `total_failures`, `total_timeouts` is
  incremented for an admitted request (never for a short-circuited one).

A `request` whose `outcome` is not in the closed set raises a malformed
input (the binary must exit non-zero); the schema in `/app/schemas/` is the
source of truth.

## `tick`

Fields: none.

A `tick` event:

1. Increments the global tick by 1 (`current_global_tick += 1`).
2. Iterates every endpoint in ASCII-sorted `id` order. For each endpoint:
   - if the endpoint is currently in `OPEN` and `current_global_tick -
     tick_entered_open >= effective recovery_ticks`, transition the
     endpoint to `HALF_OPEN` with `reason == "recovery_timeout"`. Clear
     `tick_entered_open` to null. Reset probe counters to zero.
   - if `policy.sliding_strategy == "time_based"`, prune the endpoint's
     sliding window: drop any leading entries whose `tick_observed` is
     strictly less than `current_global_tick - effective window_size + 1`.

The pruning runs even when the endpoint is in `OPEN` or `HALF_OPEN` (so that
when the endpoint later returns to `CLOSED` and then `OPEN`, the window is
not stale). The transition check happens on the tick that crosses the
threshold for the first time, not before; an endpoint with `recovery_ticks
== 0` will transition on the very next tick after entering `OPEN`.

## `add_endpoint`

Fields: `endpoint_id`, optional `failure_threshold_pct`, `window_size`,
`half_open_max_probes`, `recovery_ticks` (any of which may be `null` to
defer to `policy.default_*`).

If `endpoint_id` already exists, emit `E_DUPLICATE_ENDPOINT` and stop. No
state change, no transition.

Otherwise, create a new endpoint in `CLOSED` with the supplied overrides,
empty window, zero probe counters, zero running counters, and
`tick_entered_open = null`.

## `remove_endpoint`

Fields: `endpoint_id`.

If `endpoint_id` is not present, emit `E_ENDPOINT_NOT_FOUND` and stop.
Otherwise, delete the endpoint and all of its in-memory state. Existing
rows in `state_transitions`, `request_log`, and `diagnostics` that
reference the removed endpoint are preserved -- the simulator only
removes the endpoint from `final_endpoints` and from any further event
processing. A subsequent `add_endpoint` for the same id is admitted
(unlike, say, region ids which are sticky).

## `config_update`

Fields: `endpoint_id`, optional `failure_threshold_pct`, `window_size`,
`half_open_max_probes`, `recovery_ticks`. Each optional field that is
present (including explicit `null`) overwrites the endpoint's stored
override; absent fields leave the existing override untouched.

If `endpoint_id` is not present, emit `E_ENDPOINT_NOT_FOUND` and stop.
Otherwise, replace the named overrides on the endpoint. The change takes
effect immediately on the next event for that endpoint (so a tick or
request later in the same trace will use the new effective thresholds).

A `config_update` never triggers a state transition by itself, even if the
new thresholds would have made the current window threshold-breaching --
the threshold check is only applied on the post-insert path of a
`CLOSED`-state `request` event.

## `force_open`

Fields: `endpoint_id`.

If `endpoint_id` is not present, emit `E_ENDPOINT_NOT_FOUND` and stop.

Otherwise, if the endpoint is already in `OPEN`, emit
`W_FORCED_OPEN_NOOP`. Reset probe counters to zero. Update
`tick_entered_open` to the current global tick (so the recovery countdown
restarts). The sliding window is preserved. No `state_transitions` row is
emitted.

If the endpoint was in `CLOSED` or `HALF_OPEN`, emit `W_FORCED_OPEN`,
transition to `OPEN` with `reason == "manual_open"`, set
`tick_entered_open = current_global_tick`, reset probe counters to zero.
The sliding window is preserved.

## `force_close`

Fields: `endpoint_id`.

If `endpoint_id` is not present, emit `E_ENDPOINT_NOT_FOUND` and stop.

Otherwise, if the endpoint is already in `CLOSED`, emit
`W_FORCED_CLOSE_NOOP`. Reset probe counters to zero. Clear the sliding
window. `tick_entered_open` stays `null`. No `state_transitions` row.

If the endpoint was in `OPEN` or `HALF_OPEN`, emit `W_FORCED_CLOSE`,
transition to `CLOSED` with `reason == "manual_close"`, clear
`tick_entered_open` to null, reset probe counters to zero, clear the
sliding window.
