# Compose start-order audit (normative)

All inputs are UTF-8 JSON. The audit day is `pool_state.current_day` (integer). Never mutate anything under `/app/compose_plans/`.

## Stacks

Each file in `stacks/` is one object with `stack_id`, `cluster_id`, `tier` (`production`, `staging`, or `development`), `active_profiles` (array of profile name strings), `already_started` (array of service id strings already started), `rollout_windows` (array of inclusive `[start_day, end_day]` integer pairs), and `health_streak` (object mapping service id strings to integers: consecutive healthy days recorded through day `current_day - 1`; absent keys count as 0).

## Services

Each file in `services/` is one object with `service_id`, `profiles` (array of profile name strings), `depends_on` (array of service id strings), `priority` (integer; lower values are more preferred when choosing at most one service to start today), `warmup_cost` (integer ≥ 0), and `health_days_required` (integer ≥ 0).

## Clusters

Each file in `clusters/` is one object with `cluster_id`, `start_credits` (integer ≥ 0 shared pool for the audit day), and `max_starts_per_day` (integer ≥ 0).

## Policy

`policy.json` contains `tier_rank` (map tier → integer; lower rank starts earlier under capacity limits), `tier_calendar` (map tier → array of inclusive `[start_day, end_day]` pairs), and `max_warmup_cost_per_stack` (map tier → integer; a service whose `warmup_cost` exceeds this ceiling is not a candidate for stacks of that tier).

## Effective rollout window

For a stack, build every inclusive interval `[max(s0, t0), min(s1, t1)]` where `[s0, s1]` is a stack `rollout_windows` entry and `[t0, t1]` is a `tier_calendar[tier]` entry. Discard intervals where `max > min`. The audit day is inside the window iff it lies in at least one surviving interval.

## Profile overlap

A service profile-overlaps a stack when at least one string appears in both `service.profiles` and `stack.active_profiles`.

## Incidents

Read `incident_log.events`. Keep only events with `accepted == true` and `event.day <= current_day`. Sort kept events by ascending `(day, event_id)` and process in that order.

Supported `kind` values:

- `stack_compromise`: requires `stack_id`. When `event.day <= current_day`, that stack cannot start any service; its `stack_status` is `quarantined`.
- `freeze_cluster`: requires `cluster_id`. When `event.day <= current_day`, every stack in that cluster cannot start; `stack_status` is `cluster_frozen`.
- `service_embargo`: requires `service_id`. Optional integer `start_day` (default `event.day`) and required integer `end_day`. On audit days `d` with `start_day <= d <= end_day`, the service is not a candidate for any stack.
- `cap_bump`: requires `cluster_id` and integer `delta`. Add `delta` to that cluster's effective `max_starts_per_day` for the capacity pass (additive across kept events).
- `credit_grant`: requires `cluster_id` and integer `delta`. Add `delta` to that cluster's starting `start_credits` pool before the warmup pass (additive across kept events).

Unknown kinds, malformed required fields, or `accepted` not true are ignored (not listed in the journal). Events with `day > current_day` are also ignored.

## Service candidacy (per stack, before capacity)

A service is a candidate when:

1. It is not already listed in `already_started`.
2. Every id in `depends_on` is present in `already_started`.
3. The audit day lies in the stack's effective rollout window.
4. No kept `service_embargo` covers the audit day for this service id.
5. The stack is not under an active `stack_compromise` on the audit day.
6. The stack's cluster is not under an active `freeze_cluster` on the audit day.
7. `warmup_cost` is not greater than `max_warmup_cost_per_stack[tier]`.
8. The service profile-overlaps the stack.
9. `health_streak[service_id]` (or 0 when absent) is greater than or equal to `health_days_required`.

When at least one candidate remains, the chosen service is the candidate with the smallest `priority`; ties break by ascending ASCII `service_id`.

## Cluster capacity and warmup pass

Consider stacks that are not `quarantined` or `cluster_frozen` and that have a chosen service after the rules above. Sort those stacks by ascending `(tier_rank[tier], stack_id)`.

Walk stacks in that order. For each stack, let `C` be its cluster. Let `effective_cap` be that cluster's base `max_starts_per_day` plus the sum of `delta` from kept `cap_bump` events targeting `C`. Let `start_credits_start` be the cluster file's `start_credits` plus the sum of `delta` from kept `credit_grant` events targeting `C`, minus warmup costs already debited earlier in this pass.

If the count of stacks already assigned a start today in cluster `C` is greater than or equal to `effective_cap`, the stack is `deferred_capacity`, assigns no service today, and the blocked row for its chosen service must cite `capacity_deferred`.

Otherwise, if `start_credits_remaining` for `C` is strictly less than the chosen service's `warmup_cost`, the stack is `warmup_deferred`, assigns no service today, and the blocked row for its chosen service must cite `warmup_deferred`.

Otherwise debit the service's `warmup_cost` from `start_credits_remaining`, increment that cluster's scheduled count, and set `stack_status` `scheduled` with `scheduled_service` equal to the chosen service id.

Stacks with no startable service and not quarantined or cluster-frozen are `idle`.

## Blocked candidate ledger

For every stack, for every service file id that is not in `already_started` and was not scheduled today, emit one `blocked_candidates` row with the single highest-precedence reason among:

| Reason | Condition |
|--------|-----------|
| `quarantine` | active compromise on stack |
| `cluster_frozen` | active freeze on stack cluster |
| `capacity_deferred` | stack ended `deferred_capacity` for this service |
| `warmup_deferred` | stack ended `warmup_deferred` for this service |
| `embargoed` | embargo covers audit day |
| `outside_window` | audit day outside effective rollout window |
| `profile_mismatch` | service does not profile-overlap stack |
| `insufficient_health` | health streak below `health_days_required` while profile/window/embargo otherwise pass |
| `missing_dependency` | some `depends_on` not started |
| `warmup_over_budget` | service `warmup_cost` exceeds tier ceiling while dependencies/window/embargo/profile/health otherwise pass |

Precedence order above is strict (top wins). Sort rows by ascending `service_id`. Use an empty array when there are no pending services.

## Outputs (five files under `/app/audit/`)

Canonical JSON: UTF-8, two-space indent, ASCII only, object keys sorted lexicographically at every object depth, colon plus single space, exactly one trailing newline at EOF.

### stack_plan.json

- `stacks`: array sorted by ascending `stack_id`. Each object: `blocked_candidates` (array of `{service_id, reason}` sorted by `service_id`), `scheduled_service` (string or JSON null), `stack_id`, `stack_status` (`quarantined`, `cluster_frozen`, `deferred_capacity`, `warmup_deferred`, `scheduled`, `idle`), `tier`, `cluster_id`.

### cluster_ledger.json

- `clusters`: map keyed by `cluster_id` sorted ascending. Each value: `effective_cap` (int), `start_credits_remaining` (int after debits), `start_credits_start` (int before debits), `max_starts_per_day` (int base from file), `stacks_deferred_capacity` (int), `stacks_deferred_warmup` (int), `stacks_scheduled` (int).

### service_matrix.json

- `services`: array sorted by ascending `service_id`. Each object: `service_id`, `stacks_blocked` (int count of blocked rows citing this service), `stacks_scheduled` (int count of stacks that scheduled this service today).

### incident_journal.json

- `applied_events`: kept incidents in process order; each object includes `day`, `event_id`, `kind`, plus kind-specific fields (`stack_id`, `cluster_id`, `service_id`, `delta`, `start_day`, `end_day`) omitting absent ones. Keys sorted lexicographically inside each object.

### summary.json

Sorted keys: `applied_incident_events`, `clusters_total`, `deferred_stacks`, `frozen_stacks`, `idle_stacks`, `ignored_incident_events`, `quarantined_stacks`, `scheduled_services_today`, `scheduled_stacks`, `services_total`, `stacks_total`, `warmup_deferred_stacks`.

Counts: `stacks_total` is stack file count; `services_total` is service file count; `clusters_total` is cluster file count; `quarantined_stacks`, `frozen_stacks`, `deferred_stacks`, `warmup_deferred_stacks`, `scheduled_stacks`, and `idle_stacks` partition stacks by final `stack_status`; `scheduled_services_today` is count of non-null `scheduled_service`; `ignored_incident_events` is original event count minus kept count.
