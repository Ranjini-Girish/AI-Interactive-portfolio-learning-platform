# SLO burn window audit (normative)

All inputs are UTF-8 JSON. The audit day is `pool_state.current_day` (integer). Never mutate any file under the read-root directory tree used for this audit (the path resolved from the task prompt when overrides are set, otherwise `/app/slo-matrix/`).

## Service minutes

Each file `services/<service_id>.json` contains `service_id`, `tier` in {`gold`,`silver`,`bronze`}, and `minutes_by_day` mapping decimal day strings to objects with integer `bad_minutes` (≥ 0). Days outside any computed window are ignored. Missing days inside a window count as 0 bad minutes.

## Dependency edges

`consumers/edges.json` contains `edges`: array of objects with `consumer_id` and `producer_id` (strings). Malformed edge objects (missing either field) are ignored.

## Incidents

Read `incident_log.events`. Keep only events with `accepted == true` and `day <= current_day`. Sort kept events by ascending `(day, event_id)` and process in that order.

Supported kinds (others ignored):

- `tier_budget_delta`: `target_tier` in {`gold`,`silver`,`bronze`} and integer `delta_minutes`. Adds `delta_minutes` to the running tier error-budget total for all later per-service budget work (additive across events).
- `burn_freeze`: `service_id`, integer `freeze_start_day`, integer `freeze_end_day` (inclusive). For that service, every day `d` with `freeze_start_day <= d <= freeze_end_day` contributes 0 bad minutes when summing any window (multiple freezes union).
- `service_compromise`: `service_id`. Cross-cutting override below.
- `slo_review_override`: `service_id` and `target_status` in {`ok`,`warning`,`breached`}. After numeric status is known, set this service’s final `slo_status` to `target_status` and include literal `slo_review_override` in `reasons` (even when `target_status` equals the numeric status).

Malformed events (missing required fields, wrong types) are ignored like unsupported kinds.

## Tier error budget

`base_budget = policy.error_budget_minutes_by_tier[tier]`. Add all applied `tier_budget_delta.delta_minutes` for that tier. Result is `error_budget_minutes` (minimum 1: if sum ≤ 0, use 1).

## Window burn (integer only)

Let `S = policy.slow_window_days` and `F = policy.fast_window_days` (each ≥ 1).

For window length `W`, inclusive days are integers `d` with `current_day - (W - 1) <= d <= current_day`.

`consumed_bad(W)` = sum of effective bad minutes for days in that window.

`allowed_bad(W) = (error_budget_minutes * W) // S` (floor division).

`burn_rate_milli(W) = (consumed_bad(W) * 1000) // max(1, allowed_bad(W))`.

Emit `burn_rate_milli_fast` and `burn_rate_milli_slow` using `W = F` and `W = S`.

`effective_burn_rate_milli = max(burn_rate_milli_fast, burn_rate_milli_slow)`.

`remaining_budget_minutes = max(0, allowed_bad(S) - consumed_bad(S))` before compromise override.

## Numeric slo_status

Read `policy.burn_threshold_milli_by_tier[tier]` with integer fields `warning` and `critical` where `warning < critical`.

From `effective_burn_rate_milli`:

- `ok` if below `warning`
- `warning` if `warning <= value < critical`
- `breached` if `value >= critical`

## Reasons

Start empty. After numeric status, if a kept `service_compromise` names this `service_id`, set `slo_status` to `breached`, `remaining_budget_minutes` to 0, and append `service_compromise`.

If a kept `slo_review_override` names this `service_id` (latest event wins on duplicate service), set `slo_status` to `target_status` and append `slo_review_override`.

`reasons` must be strictly increasing ASCII order, unique strings.

## Dependency taint

Let `compromised` be the set of `service_id` values with a kept `service_compromise`.

For each `consumer_id` appearing as `consumer_id` in any well-formed edge, compute the set of `producer_id` values reachable by following edges from any compromised service along producer→consumer direction (transitive closure). `taint_status` is `inherited_compromise` if that set is non-empty, else `clean`. `compromised_producers` is the sorted unique ASCII list of producers in that reachable set (empty when `clean`).

## Outputs (five UTF-8 JSON files in the audit directory)

Canonical JSON: UTF-8, two-space indent, ASCII only, object keys sorted lexicographically at every depth, colon plus single space, exactly one trailing newline at EOF.

### burn_report.json

`services`: array sorted by `service_id` ascending. Each object: `allowed_bad_minutes_slow`, `burn_rate_milli_fast`, `burn_rate_milli_slow`, `consumed_bad_minutes_slow`, `effective_burn_rate_milli`, `reasons`, `remaining_budget_minutes`, `service_id`, `slo_status` in {`ok`,`warning`,`breached`}, `tier`.

### tier_budgets.json

`tiers`: map with exactly keys `bronze`, `gold`, `silver`. Each value: `{ "adjusted_budget_minutes": int, "base_budget_minutes": int, "delta_sum_minutes": int }`.

### dependency_taint.json

`consumers`: array sorted by `consumer_id` ascending. Each object: `compromised_producers` (sorted strings), `consumer_id`, `taint_status` in {`clean`,`inherited_compromise`}.

### incident_journal.json

`applied_events`: array in ascending `(day, event_id)` order. Each element includes `day`, `event_id`, `kind`, plus kind-specific fields (`delta_minutes`, `target_tier`, `freeze_start_day`, `freeze_end_day`, `service_id`, `target_status`) omitting keys not required for that kind. Keys sorted inside each object.

### summary.json

Fields (sorted keys): `applied_incident_events`, `breached_services`, `compromise_services`, `ignored_incident_events`, `inherited_compromise_consumers`, `ok_services`, `services_total`, `warning_services`.

Counts follow emitted rows. `compromise_services` is the count of distinct services with kept `service_compromise`. `inherited_compromise_consumers` counts consumers with `taint_status == inherited_compromise`. `ignored_incident_events` is total log events minus kept well-formed events (including rejected, future day, unknown kind, malformed).
