# Webhook retry ledger audit (normative)

All inputs are UTF-8 JSON. The audit day is `pool_state.current_day` (integer). Never mutate anything under `/app/webhooks/`.

## Rolling window

Let `W = policy.rolling_window_days` (integer ≥ 1). The inclusive window is every integer `d` with `current_day - (W - 1) <= d <= current_day`.

Each subscription file has `outcomes_by_day` mapping decimal day strings to exactly one of `ok`, `fail`, `timeout`, or `rate_limited`. Days absent from the map are ignored.

Optional `slip_days` maps decimal day strings to integers (the scheduled day). When present for day `d`, a chargeable outcome on `d` is **not** counted if `d <= slip_days[d] + policy.grace_days_by_tier[tier]` (integer comparison). A later `failure_day_suppress` targeting that same `d` is a no-op for that pair: slip grace already removed the day from the slip-adjusted tally, so there is nothing left for that suppress entry to remove.

## Chargeable outcomes by tier

For counting `raw_chargeable` inside the window, an outcome counts only when it is chargeable for the subscription tier:

| tier   | chargeable outcomes                          |
|--------|----------------------------------------------|
| gold   | `fail`, `timeout`                            |
| silver | `fail`, `timeout`, `rate_limited`            |
| bronze | `fail`, `timeout` (`rate_limited` excluded)  |

## Incidents

Read `incident_log.events` (array). Keep only events with `accepted == true` and `event.day <= current_day`. Sort kept events by ascending `(day, event_id)` and process in that order.

Supported `kind` values:

- `tier_retry_delta`: fields `target_tier` ∈ {`gold`,`silver`,`bronze`} and integer `delta`. Adds `delta` to the running retry budget for that tier (additive across events; a tier's `delta_sum` is the signed sum, may be negative).
- `failure_day_suppress`: fields `subscription_id` and `days` (array of integers). For each integer `d` in `days`, if `d` is in the rolling window for the named subscription, the outcome on `d` is chargeable for its tier, the day is **not** excluded by the `slip_days` rule above, and the `(subscription_id, d)` pair has not already been consumed by a previously-processed `failure_day_suppress` event in `(day, event_id)` order, decrement the post-slip running failure tally used for suppressions by 1 (floor at 0). Each `(subscription_id, d)` pair contributes at most one subtraction across all kept `failure_day_suppress` events combined: the first event in `(day, event_id)` order to cover that pair consumes it, and any later event referencing the same pair is a silent no-op for that pair. A slip-excused pair is never consumed and never decrements the tally.
- `bronze_surge`: no extra targets. While this event is among kept events, every subscription whose `tier` is `bronze` adds integer `policy.bronze_surge_extra_failures` to `effective_failures` after suppressions below.
- `endpoint_compromise`: fields `endpoint_id`. After all numeric work for every subscription on that endpoint, those subscriptions must emit `disposition` `quarantined`, `retries_exhausted` true, and `reasons` must include `endpoint_compromise` (even if other reasons also apply).
- `force_exhausted`: fields `subscription_id`. After numeric work for that subscription, if kept, emit `disposition` `exhausted`, `retries_exhausted` true, and include `force_exhausted_incident` in `reasons`.

Events with unknown `kind`, unknown `accepted` type, or missing required fields for their kind are ignored entirely.

## Endpoints and signing

Each subscription references `endpoint_id` naming `endpoints/<id>.json` (stem equals `endpoint_id`). Missing file treats `rate_limited` as false.

Each endpoint has `signing_profile` (stem of `signing_profiles/<stem>.json`). Missing profile file yields `effective_signing_key_id` `none`.

Each signing profile has `keys`: array of `{ "key_id": string, "valid_from_day": int }`. Let `cutoff = current_day - policy.signing_rotation_lag_days`. The effective key is the lexicographically greatest `key_id` among keys with `valid_from_day <= cutoff`. If none qualify, use `none`.

## Retry budget

`base_budget = policy.retries_by_tier[tier]`. Add all applied `tier_retry_delta.delta` for that tier (the signed `delta_sum`, which may be negative). `adjusted_retry_budget = max(1, base_budget + delta_sum)`.

## Previous-window carryover

`pool_state.previous_window_carryover` is an optional map from `subscription_id` to a non-negative integer; absence of the map or absence of a key is treated as `0`. Let `raw_carryover[sub] = previous_window_carryover[sub]` (defaulting to `0`).

Carryover is conditionally suppressed per-subscription: if the `delta_sum` for the subscription's tier is **strictly negative** (i.e. the tier had its retry budget tightened by net `tier_retry_delta` events in this audit), the carryover is treated as `0` for that subscription. Otherwise the carryover passes through unchanged. The applied amount is reported in each subscription row as the integer `carryover_failures` (always present; `0` when suppressed, missing from the map, or `0` in the map).

## Penalties and ordering

1. `raw_chargeable` counts chargeable outcomes in the window, honoring `slip_days` grace per day.
2. Apply all `failure_day_suppress` subtractions (floor 0, with the cross-event pair-deduplication rule above).
3. If tier is `bronze` and any kept `bronze_surge` exists, add `policy.bronze_surge_extra_failures` (default 0 if missing).
4. If tier is `gold` and the endpoint's `rate_limited` is true, add `policy.gold_endpoint_throttle_extra_failures` (default 0 if missing).
5. Add `carryover_failures` (after the per-subscription suppression rule above).
6. The sum is `effective_failures`.

## Disposition and retries_exhausted

If a kept `endpoint_compromise` targets this subscription's endpoint, set `disposition` to `quarantined` and `retries_exhausted` true.

Else if a kept `force_exhausted` targets this `subscription_id`, set `disposition` to `exhausted` and `retries_exhausted` true.

Else if `effective_failures >= adjusted_retry_budget`, set `disposition` to `exhausted` and `retries_exhausted` true.

Else set `disposition` to `active` and `retries_exhausted` false.

## Reasons array

When `disposition` is `active`, emit `"reasons": []`.

Otherwise include:

- `endpoint_compromise` when quarantined for that reason.
- `force_exhausted_incident` when forced exhausted.
- `retry_budget_exhausted` when `effective_failures >= adjusted_retry_budget` would hold ignoring force and quarantine flags.
- `bronze_surge_active` when bronze surge applied and `policy.bronze_surge_extra_failures > 0`.
- `gold_endpoint_throttle_penalty` when gold throttle penalty contributed a strictly positive amount.
- `previous_window_carryover` when `carryover_failures > 0` AND `effective_failures >= adjusted_retry_budget` would hold ignoring force and quarantine flags.

`reasons` must be strictly increasing ASCII order, unique strings.

## Outputs (five files under `/app/audit/`)

Canonical JSON: UTF-8, two-space indent, ASCII only, object keys sorted lexicographically at every object depth, colon plus single space, no trailing spaces on lines, exactly one trailing newline at EOF.

### subscription_verdicts.json

- `subscriptions`: array sorted by ascending `subscription_id`. Each object: `subscription_id`, `tier`, `endpoint_id`, `raw_chargeable` (int), `carryover_failures` (int), `effective_failures` (int), `adjusted_retry_budget` (int), `effective_signing_key_id` (string), `disposition` (`active`|`exhausted`|`quarantined`), `retries_exhausted` (bool), `reasons` (array).

### tier_retry_budgets.json

- `tiers`: map with exactly keys `bronze`, `gold`, `silver`. Each value: `{ "adjusted_retry_budget": int, "base_budget": int, "delta_sum": int }`.

### incident_journal.json

- `applied_events`: array in ascending `(day, event_id)` order. Each element includes `day`, `event_id`, `kind`, and kind-specific optional fields (`delta`, `target_tier`, `days`, `subscription_id`, `endpoint_id`) with keys sorted inside each object.

### endpoint_touchpoints.json

- `endpoints`: map keyed by `endpoint_id` sorted ascending. Each value: `{ "rate_limited": bool, "referencing_subscriptions": [ ...ids sorted ascending... ] }`.

### summary.json

Fields: `applied_incident_events` (int), `bronze_surge_active` (bool), `endpoints_total` (int), `exhausted_subscriptions` (int), `gold_subscriptions_with_throttle_penalty` (int), `ignored_incident_events` (int), `quarantined_subscriptions` (int), `subscriptions_total` (int).
