# Hedge call latency audit

Inputs live beside this file. Read `policy.json`, `pool_state.json`, `incidents.json`, every `*.json` under `calls/`, every `*.json` under `overrides/`, and every non-empty line in `anchors/*.txt`. Files under `ledger/` are packaging only.

## Canonical JSON

Emit every artifact as JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Policy

- `hedge_delay_ms_per_tier` maps tier name to integer milliseconds waited before a hedge replica may start.
- `hedge_budget_per_window` maps tier name to the maximum hedges that may fire per audit window.
- `sla_max_ms_per_tier` maps tier name to inclusive SLA ceiling for `effective_latency_ms`.
- `supported_incident_kinds` lists incident kinds the journal accepts.
- `window_ms` is copied into outputs that expose a window.

## Pool state

- `current_day` gates incidents: only events with `day <= current_day` are eligible.

## Override merge

Walk `overrides/*.json` in ascending ASCII basename order. Sum `delay_bump_ms[tier]` into per-tier bump totals and sum `budget_credit[tier]` into per-tier credit totals. Effective per-tier delay is `hedge_delay_ms_per_tier[tier] + bump`. Effective per-tier budget cap is `hedge_budget_per_window[tier] + credit`.

## Incidents

Each event has `day`, `event_id`, `kind`, `scope`, and `accepted` (default true when absent). Reject when `accepted` is false (`reason=accepted_false`), when `day > current_day` (`reason=future_day`), or when `kind` is not listed in `supported_incident_kinds` (`reason=unsupported_kind`). Accepted events apply in ascending `(day, event_id)` order:

- `hedge_compromise` adds `scope.correlation_root` to disabled roots and/or `scope.call_id` to disabled call ids.
- `force_budget_credit` adds `scope.credit` to the tier named by `scope.service_tier`.
- `hedge_delay_bump` adds `scope.bump_ms` to the tier named by `scope.service_tier`.

## Anchor overrides

Each non-empty `anchors/*.txt` line is two tokens: `call_id` then `hedge_disabled`. That call id is disabled individually (it does not disable siblings sharing a correlation root).

## Disabled calls

A call is disabled when its `call_id` is listed or its `correlation_root` matches a disabled root. Disabled calls never fire hedges. When `status` is `success`, still set `effective_latency_ms` to `primary_latency_ms` with `latency_source=primary`. When `status` is `primary_timeout`, leave `effective_latency_ms` and `latency_source` null. Verdict is always `hedge_disabled`.

## Hedge trigger

For non-disabled calls with `status=error`, verdict is `error` with null latencies and `hedge_fired=false`.

Otherwise a hedge trigger is true when `hedge_latency_ms` is not null and either (`status=success` and `primary_latency_ms` is strictly greater than the tier effective delay) or `status=primary_timeout`.

When trigger is true and `hedges_fired` for that tier is already at the tier budget cap, set `hedge_fired=false`, verdict `hedge_budget_exhausted`, and use primary-only effective latency on successful primaries (null on primary timeouts).

When trigger is true and budget remains, set `hedge_fired=true`, increment the tier hedge counter, and set `effective_latency_ms` to the minimum of primary and hedge on success, or to `hedge_latency_ms` on primary timeout. Set `latency_source` to `hedge` when the hedge latency wins the minimum or on primary timeout; otherwise `primary`.

When trigger is false, `hedge_fired=false`. On success use primary latency and `latency_source=primary`. On primary timeout with null hedge path, leave effective latency null.

## SLA verdict

After effective latency is chosen (unless verdict is already `error`, `hedge_disabled`, or `hedge_budget_exhausted`), set `met_sla` when `effective_latency_ms` is not null and `effective_latency_ms <= sla_max_ms_per_tier[service_tier]`, else `missed_sla`. Null effective latency is `missed_sla`.

## Outputs

Write five files to the audit directory:

1. `call_verdicts.json` with keys `calls` then `window_ms`. Each call row includes `call_id`, `correlation_root`, `effective_latency_ms`, `hedge_fired`, `hedge_latency_ms`, `latency_source`, `primary_latency_ms`, `service_tier`, and `verdict`. Sort `calls` by `call_id` ascending.
2. `hedge_budget.json` with keys `tiers` then `window_ms`. `tiers` maps each tier to `budget_cap`, `budget_credit`, `delay_bump_ms`, `effective_delay_ms`, and `hedges_fired`. Tier keys sorted lexicographically.
3. `compromise_report.json` with `disabled_call_ids` and `disabled_correlation_roots`, each sorted ascending.
4. `incident_journal.json` with `accepted` and `ignored` arrays sorted by `(day, event_id)`.
5. `summary.json` with `calls_total`, `hedge_fired_total`, `service_tiers` (fixed `["bronze","gold","silver"]`), `verdict_counts` (keys sorted lexicographically mapping verdict name to count), and `window_ms`.

## Tooling

Read `HCL_DATA_DIR` defaulting to `/app/hedgecalls` and `HCL_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
