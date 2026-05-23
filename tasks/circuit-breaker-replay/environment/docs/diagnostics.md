# Diagnostic Code Catalogue

The simulator emits zero or more diagnostic codes per event. Diagnostics
are grouped per `seq` in `diagnostics.json` and within each event sorted
by `(severity_rank, code, endpoint_id)`. The severity ranks are:

| severity | rank |
| -------- | ---- |
| error    | 0    |
| warning  | 1    |
| note     | 2    |

The closed set of diagnostic codes is below. The simulator must use
exactly these codes; no other code may appear in `diagnostics.events`.

| Code                       | Severity | Triggers when                                                                                                                                                |
| -------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `E_ENDPOINT_NOT_FOUND`     | error    | `request`, `remove_endpoint`, `config_update`, `force_open`, or `force_close` references an `endpoint_id` that is not currently present.                      |
| `E_DUPLICATE_ENDPOINT`     | error    | `add_endpoint` is processed with an `endpoint_id` that is already present.                                                                                    |
| `W_FORCED_OPEN`            | warning  | A `force_open` event actually changed the target endpoint's state from `CLOSED` or `HALF_OPEN` to `OPEN`.                                                    |
| `W_FORCED_OPEN_NOOP`       | warning  | A `force_open` event was applied to an endpoint already in `OPEN`. The probe counters and `tick_entered_open` are still refreshed, but no transition is emitted. |
| `W_FORCED_CLOSE`           | warning  | A `force_close` event actually changed the target endpoint's state from `OPEN` or `HALF_OPEN` to `CLOSED`.                                                   |
| `W_FORCED_CLOSE_NOOP`      | warning  | A `force_close` event was applied to an endpoint already in `CLOSED`. Probe counters / window are still cleared, but no transition is emitted.                |
| `N_TRANSITION_TO_OPEN`     | note     | The endpoint transitioned to `OPEN` for any reason (`threshold_breach`, `probe_failure`, `manual_open`).                                                      |
| `N_TRANSITION_TO_HALF_OPEN`| note     | The endpoint transitioned to `HALF_OPEN` (`recovery_timeout`).                                                                                                |
| `N_TRANSITION_TO_CLOSED`   | note     | The endpoint transitioned to `CLOSED` (`probe_success_quota` or `manual_close`).                                                                              |
| `N_PROBE_ADMITTED`         | note     | A `request` was admitted as a probe in `HALF_OPEN`.                                                                                                          |
| `N_REQUEST_SHORT_CIRCUITED`| note     | A `request` was short-circuited in `OPEN`.                                                                                                                   |

## Co-emission rules

- `W_FORCED_OPEN` always co-emits `N_TRANSITION_TO_OPEN` for the same `seq`.
- `W_FORCED_CLOSE` always co-emits `N_TRANSITION_TO_CLOSED` for the same `seq`.
- A `request` that triggers a `CLOSED -> OPEN` threshold breach co-emits
  `N_TRANSITION_TO_OPEN` alongside any per-request notes for that same
  `seq` (there is no per-request note for a normal admitted request in
  `CLOSED`; only the transition note when one fires).
- A `request` admitted in `HALF_OPEN` always emits `N_PROBE_ADMITTED`. If
  the probe verdict triggers a transition, the transition note
  (`N_TRANSITION_TO_OPEN` or `N_TRANSITION_TO_CLOSED`) is appended to the
  same `seq`.
- A `request` short-circuited in `OPEN` always emits
  `N_REQUEST_SHORT_CIRCUITED`. It never co-emits a transition note (a
  later `tick` event is what eventually moves the endpoint to
  `HALF_OPEN`).

## Diagnostic ordering

Within the diagnostics list of a single event, entries are sorted by
`(severity_rank, code, endpoint_id)` ascending. Across events, the
`diagnostics.events` list itself is sorted by `seq` ascending. An event
with no diagnostics produces no entry in `diagnostics.events`.
