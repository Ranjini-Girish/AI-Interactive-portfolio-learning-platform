# Per-endpoint State Machine

Every endpoint is in exactly one of three states: `CLOSED` (the default,
healthy state), `OPEN` (the breaker is tripped, requests short-circuit),
and `HALF_OPEN` (the breaker is probing the downstream after a recovery
window).

## Effective thresholds

For any threshold field on an endpoint, the effective value is the
endpoint's own override when non-null, else `policy.default_*`. The four
per-endpoint thresholds and their fallbacks are:

| endpoint field           | policy default                      |
| ------------------------ | ----------------------------------- |
| `failure_threshold_pct`  | `policy.default_failure_threshold_pct`  |
| `window_size`            | `policy.default_window_size`            |
| `half_open_max_probes`   | `policy.default_half_open_max_probes`   |
| `recovery_ticks`         | `policy.default_recovery_ticks`         |

These are recomputed every event (so a `config_update` that nulls an
override starts taking effect immediately on the next event for that
endpoint). The `final_endpoints.json` row reports the *effective*
thresholds at trace end under fields named `current_failure_threshold_pct`,
`current_window_size`, `current_half_open_max_probes`, and
`current_recovery_ticks`.

## Sliding window

Each endpoint carries a deque of recent outcomes observed while the endpoint
was in `CLOSED`. The deque holds tuples of (outcome, tick_observed). It is
extended only by `request` events processed in the `CLOSED` state. Probe
outcomes from `HALF_OPEN` and short-circuited requests in `OPEN` are NOT
added to the window.

Two sliding strategies are supported via `policy.sliding_strategy`:

- `"count_based"`: keep at most `window_size` entries; the oldest entries
  are evicted from the front when the deque length exceeds `window_size`.
  Tick-based eviction does not occur.
- `"time_based"`: every entry whose `tick_observed` is strictly less than
  `current_global_tick - window_size + 1` is evicted from the front. The
  eviction happens on every `tick` event AND immediately before any
  `CLOSED`-state `request` event records its outcome (so the threshold
  check sees a fresh window). The deque length is unbounded; only age
  bounds entries.

The `failure_count_in_window` is the number of entries in the window whose
outcome is `failure` or `timeout` (treated identically). The
`requests_in_window` is the total deque length.

## CLOSED -> OPEN

In `CLOSED` every `request` is admitted. The outcome is recorded in the
window. After insertion (and any `time_based` pruning), the simulator
checks the threshold:

- if `requests_in_window >= policy.min_window_observations` AND
  `floor(failure_count_in_window * 100 / requests_in_window) >= effective failure_threshold_pct`,
  the endpoint transitions `CLOSED -> OPEN` with `reason == "threshold_breach"`
  and `tick_entered_open` is set to the current global tick.

The sliding window itself is not cleared on the `CLOSED -> OPEN` transition;
it is preserved so the operator can audit the breach. It will only be
cleared the next time the endpoint re-enters `CLOSED`.

## OPEN -> HALF_OPEN

`request` events do not change `OPEN` state. They are short-circuited and
recorded in `request_log` with `state_at_admission == "OPEN"` and
`admission == "short_circuited"`.

`tick` events advance the global tick. After incrementing the global tick,
the simulator scans every `OPEN` endpoint and transitions
`OPEN -> HALF_OPEN` (with `reason == "recovery_timeout"`) for any endpoint
where `current_global_tick - tick_entered_open >= effective recovery_ticks`.
Endpoints become `HALF_OPEN` in ASCII-sorted `id` order, so two endpoints
that simultaneously become eligible produce stable transition orderings.
Each such transition resets `probes_used`, `probe_successes`, and
`probe_failures` to zero. `tick_entered_open` is cleared (set back to
`null`) on entering `HALF_OPEN`.

## HALF_OPEN -> OPEN or HALF_OPEN -> CLOSED

In `HALF_OPEN` every `request` is admitted as a probe. The request is
recorded in `request_log` with `state_at_admission == "HALF_OPEN"` and
`admission == "probe_admitted"`. Probe outcomes do not enter the
sliding window.

After admission, the simulator updates probe counters:

- `probes_used` increments by 1.
- on `success`: `probe_successes` increments by 1.
- on `failure` or `timeout`: `probe_failures` increments by 1.

Then it applies the verdict in this exact order:

1. If `probe_failures >= 1`: transition `HALF_OPEN -> OPEN` with
   `reason == "probe_failure"`. Reset `probes_used`, `probe_successes`,
   `probe_failures` to zero. Set `tick_entered_open` to the current global
   tick.
2. Else if `probe_successes >= effective half_open_max_probes`: transition
   `HALF_OPEN -> CLOSED` with `reason == "probe_success_quota"`. Clear the
   sliding window. Reset `probes_used`, `probe_successes`, `probe_failures`
   to zero.
3. Else: stay in `HALF_OPEN` with the updated probe counters.

Because the verdict is applied immediately after each probe, an endpoint
in `HALF_OPEN` never observes more than `effective half_open_max_probes`
back-to-back successful probes before transitioning to `CLOSED`. There is
no path that admits a probe and then leaves the endpoint in `HALF_OPEN`
with `probes_used >= half_open_max_probes`.

## Force events

`force_open` and `force_close` are operator-driven overrides. The
simulator unconditionally sets the target state and emits the matching
forced-state diagnostic (see `diagnostics.md`). Force transitions:

- `force_open`: target state `OPEN`. Reset probe counters. Set
  `tick_entered_open = current_global_tick`. Reason `manual_open`.
  The sliding window is preserved (not cleared).
- `force_close`: target state `CLOSED`. Reset probe counters. Clear
  `tick_entered_open` to `null`. Reason `manual_close`. The sliding
  window is cleared.

A force event whose target state already matches the endpoint's current
state still emits its diagnostic but is recorded with `reason ==
"manual_open"` / `"manual_close"` only if a state actually changed.
When the state did not change, the event emits the documented
`*_NOOP` diagnostic and adds no entry to `state_transitions`.

`add_endpoint` with thresholds matching the policy defaults is admitted;
duplicates emit `E_DUPLICATE_ENDPOINT` and change nothing. `remove_endpoint`
on a missing id emits `E_ENDPOINT_NOT_FOUND` and changes nothing; on a
present id, the endpoint and all of its state are removed but its prior
contributions to running counters and to `state_transitions` /
`request_log` / `diagnostics` are retained.

## Counters

Every endpoint maintains running counters that show up in `final_endpoints`
under the names `total_admitted`, `total_short_circuited`, `total_successes`,
`total_failures`, `total_timeouts`, and `state_transition_count`. The
relationships among them are exact:

- `total_admitted + total_short_circuited` equals the total `request`
  events targeting the endpoint that were not rejected with a `E_*`
  diagnostic.
- `total_successes + total_failures + total_timeouts` equals
  `total_admitted` (short-circuited requests do not increment the
  outcome-specific counters because they were never executed).
- `state_transition_count` equals the number of `state_transitions`
  entries whose `endpoint_id` matches.
