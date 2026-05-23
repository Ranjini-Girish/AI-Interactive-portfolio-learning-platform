# Breaker ledger audit (normative)

All inputs are UTF-8 JSON. The audit day is `pool_state.current_day` (integer). Never mutate anything under `/app/breakers/`.

## Rolling window

Let `W = policy.rolling_window_days` (integer ≥ 1). The inclusive window of days is every integer `d` with `current_day - (W - 1) <= d <= current_day`.

For each service, `outcomes_by_day` maps day strings (decimal digits only) to exactly `"ok"` or `"fail"`. Days absent from the map are ignored (neither ok nor fail). Let `raw_failures` be the count of window entries whose value is `"fail"`. Emit that integer unchanged as the `raw_failures` field in each service row; `fail_day_suppress` and tier penalties change only how `effective_failures` is derived, not this emitted tally.

## Incidents

Read `incident_log.events` (array). Keep only events with `accepted == true` and `event.day <= current_day`. Sort the kept list by ascending `(day, event_id)` and process in that order.

Supported `kind` values:

- `tier_threshold_delta`: fields `target_tier` ∈ {`gold`,`silver`,`bronze`} and integer `delta`. Adds `delta` to the running threshold for that tier for all later calculations (additive across events).
- `fail_day_suppress`: fields `service_id` and `days` (array of integers). For each integer `d` in `days`, if `d` is inside the rolling window for the named service and that service’s `outcomes_by_day` for decimal string of `d` equals `"fail"`, count one suppression credit toward that service (each matching `(service_id,d)` pair from this single event counts at most once). Suppression credits reduce the failure tally used for threshold math only; they do not change the emitted `raw_failures` field.
- `silver_spike`: no extra targets. While this event is present among the kept events, every service whose `tier` is `silver` adds integer `policy.silver_spike_extra_failures` when computing `effective_failures` (see Ordering).
- `force_open`: fields `service_id`. After all numeric work for that service, if this event is kept, the service’s emitted `computed_state` must be `open` and `reasons` must include the literal string `force_open_incident` (even if other reasons also apply). `tripped` must be true.

Events with unknown `kind`, unknown `accepted` type, or missing required fields for their kind are ignored entirely (as if not present).

## Upstreams

Each service references `upstream_id` naming a file `upstreams/<id>.json` (the `upstream_id` value is the filename stem). Missing file or missing boolean `degraded` treats `degraded` as false.

## Tier threshold

`base_threshold = policy.failure_thresholds_by_tier[tier]`. Add all applied `tier_threshold_delta.delta` values whose `target_tier` equals this service’s tier. The result is `adjusted_threshold` (minimum 1 after clamp: if the sum would be ≤ 0, use 1).

## Penalties and ordering

Let `suppressed_failures` be the value obtained by starting at `raw_failures` and processing every kept `fail_day_suppress` event in incident order: for each event targeting this service, for each suppression credit implied by that event’s rules, subtract 1 from the running tally, but never subtract when the tally is already 0 (so later credits may no-op once the tally is exhausted).

1. Start from `suppressed_failures`.
2. If the service tier is `gold` and its upstream `degraded` is true, add `policy.gold_upstream_degraded_extra_failures` (integer, default 0 if missing).
3. If the service tier is `silver` and any kept event has `kind` `silver_spike`, add `policy.silver_spike_extra_failures` (integer, default 0 if missing).
4. The sum is `effective_failures`.

Record `adjusted_threshold` as defined above.

## State and tripped

If a kept `force_open` applies to this `service_id`, set `computed_state` to `open` and `tripped` to true.

Otherwise, if `effective_failures >= adjusted_threshold`, set `computed_state` to `open` and `tripped` to true.

Otherwise set `computed_state` to `closed` and `tripped` to false.

## Reasons array

When `computed_state` is `closed`, emit `"reasons": []`.

When `computed_state` is `open` for reasons other than solely `force_open_incident`, include `threshold_exceeded` if `effective_failures >= adjusted_threshold` would hold ignoring the force flag (evaluate the numeric comparison on the same numbers; force_open does not change `effective_failures`). If upstream penalty contributed a strictly positive amount, also include `gold_upstream_degraded_penalty`. If `silver_spike` is active for this service and `policy.silver_spike_extra_failures > 0`, also include `silver_spike_active`.

`reasons` must be strictly increasing ASCII order, unique strings, even when only one entry.

## Outputs (five files under `/app/audit/`)

Canonical JSON for every output file: UTF-8, two-space indent, ASCII only, object keys sorted lexicographically at every object depth, colon plus single space after each colon, no trailing spaces on lines, exactly one trailing newline at EOF.

### service_verdicts.json

Top-level object:

- `services`: array of objects, one per input service file, sorted by ascending `service_id`.
- Each object fields: `service_id` (string), `tier`, `upstream_id`, `raw_failures` (int, the window `"fail"` count before suppression), `effective_failures` (int), `adjusted_threshold` (int), `computed_state` (`closed` or `open`), `tripped` (bool), `reasons` (array of strings, sorted unique).

### tier_thresholds.json

Object `tiers`: map with exactly keys `bronze`, `gold`, `silver` (that order in output file uses sorted keys so bronze, gold, silver). Each value is object `{ "adjusted_threshold": int, "base_threshold": int, "delta_sum": int }` where `base_threshold` comes from policy only, `delta_sum` is sum of applied tier_threshold_delta for that tier, and `adjusted_threshold` is max(1, base_threshold + delta_sum).

### incident_journal.json

Object `applied_events`: array describing each kept incident in process order. Each element: `day`, `delta` (omit unless kind is tier_threshold_delta), `days` (omit unless kind is fail_day_suppress), `event_id`, `kind`, `service_id` (omit unless kind is fail_day_suppress or force_open), `target_tier` (omit unless kind is tier_threshold_delta). Keys sorted inside each object. Sort the array by `(day asc, event_id asc)`.

### upstream_touchpoints.json

Object `upstreams`: map keyed by `upstream_id` sorted ascending. Each value: `{ "degraded": bool, "referencing_services": [ ...service_id strings sorted ascending... ] }`.

### summary.json

Fields (sorted keys): `applied_incident_events` (int), `gold_services_with_upstream_penalty` (int), `ignored_incident_events` (int), `open_services` (int), `services_total` (int), `silver_spike_active` (bool), `tripped_services` (int).

Counts: `services_total` is number of service input files. `open_services` counts services whose `computed_state` is `open`. `tripped_services` counts `tripped == true`. `gold_services_with_upstream_penalty` counts gold-tier services whose upstream is degraded AND policy.gold_upstream_degraded_extra_failures > 0 (regardless of final state). `silver_spike_active` is true iff any kept incident has kind `silver_spike`. `applied_incident_events` is length of `incident_journal.applied_events`. `ignored_incident_events` is total events in the original log minus kept count (including rejected, future day, unknown kind, malformed).

## Input layout

Services live in `services/*.json`. Each file contains one object with keys at least `service_id`, `tier`, `upstream_id`, `outcomes_by_day`. Ignore unknown keys.
