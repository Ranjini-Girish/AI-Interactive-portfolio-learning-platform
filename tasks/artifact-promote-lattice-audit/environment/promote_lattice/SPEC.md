# Artifact promote lattice audit (normative)

All inputs are UTF-8 JSON. The audit day is `pool_state.current_day` (integer). Never mutate anything under `/app/promote_lattice/`.

## Artifacts

Each file in `artifacts/` is one object with `artifact_id`, `pool` (pool id string), `current_stage` (`dev`, `staging`, or `prod`), `stage_entered_day` (integer), `depends_on` (array of artifact id strings), and `promote_priority` (integer; lower values promote earlier under capacity limits).

## Pools

Each file in `pools/` is one object with `pool_id`, `tier` (`production`, `staging`, or `development`), and `max_promotions_per_day` (integer ≥ 0).

## Policy

`policy.json` contains `stage_order` (strictly `["dev", "staging", "prod"]`), `soak_days` (map from `dev` and `staging` to integer days that must elapse in the current stage before promotion), and `tier_rank` (map tier → integer; lower rank promotes earlier under capacity limits).

## Next stage

For an artifact not at `prod`, the next stage is the successor of `current_stage` in `stage_order`. Artifacts at `prod` have no next stage.

## Stage rank

`dev` → 0, `staging` → 1, `prod` → 2.

## Incidents

Read `incident_log.events`. Keep only events with `accepted == true` and `event.day <= current_day`. Sort kept events by ascending `(day, event_id)` and process in that order.

Supported `kind` values:

- `artifact_compromise`: requires `artifact_id`. From this event's `day` onward (inclusive), that artifact cannot promote; `artifact_status` is `quarantined`.
- `freeze_pool`: requires `pool_id`. From this event's `day` onward, every artifact in that pool cannot promote; `artifact_status` is `pool_frozen`.
- `promote_embargo`: requires `artifact_id`. Optional integer `start_day` (default `event.day`) and required integer `end_day`. On audit days `d` with `start_day <= d <= end_day`, the artifact cannot promote.
- `cap_bump`: requires `pool_id` and integer `delta`. Add `delta` to that pool's effective `max_promotions_per_day` for the capacity pass (additive across kept events).

Unknown kinds, malformed required fields, or `accepted` not true are ignored (not listed in the journal).

## Promotion candidacy (per artifact, before capacity)

An artifact has a promotable next stage when:

1. `current_stage` is not `prod`.
2. Every id in `depends_on` has `stage_rank` at least the rank of the next stage.
3. `current_day - stage_entered_day >= soak_days[current_stage]` (treat missing soak entry as 0 only when `current_stage` is absent from `soak_days`; `prod` never promotes).
4. No kept `promote_embargo` covers the audit day for this artifact id.
5. The artifact is not under an active `artifact_compromise` on the audit day.
6. The artifact's pool is not under an active `freeze_pool` on the audit day.

Among promotable artifacts, sort by ascending `(tier_rank[pool.tier], promote_priority, artifact_id)` using each artifact's pool record.

## Pool capacity pass

Walk promotable artifacts in that order. For each artifact, let `P` be its pool's base `max_promotions_per_day` plus the sum of `delta` from kept `cap_bump` events targeting `P`. If the count of artifacts already assigned a promotion today in pool `P` is strictly less than `P`, assign the promotion (`artifact_status` `promoted`, `promoted_to` is the next stage). Otherwise the artifact is `deferred_capacity` and promotes nothing today.

Artifacts with no promotable next stage and not quarantined/frozen are `idle` when at `prod`, missing dependencies, or embargoed; `soak_waiting` when only soak blocks promotion; otherwise `idle`.

## Blocked promotion ledger

For every artifact with a defined next stage that was not promoted today, emit one `blocked_promotions` row with `target_stage` (the next stage string) and the single highest-precedence `reason` among:

| Reason | Condition |
|--------|-----------|
| `quarantine` | active compromise on artifact |
| `pool_frozen` | active freeze on artifact pool |
| `capacity_deferred` | artifact ended `deferred_capacity` |
| `embargoed` | embargo covers audit day |
| `soak_not_met` | soak days not satisfied |
| `missing_dependency` | some dependency below next stage rank |
| `at_terminal` | `current_stage` is `prod` |

Precedence order above is strict (top wins). Sort rows by ascending `target_stage`.

## Outputs (five files under `/app/audit/`)

Canonical JSON: UTF-8, two-space indent, ASCII only, object keys sorted lexicographically at every depth, colon plus single space, exactly one trailing newline at EOF.

### artifact_plan.json

- `artifacts`: array sorted by ascending `artifact_id`. Each object: `artifact_id`, `pool`, `current_stage`, `artifact_status` (`quarantined`, `pool_frozen`, `deferred_capacity`, `promoted`, `soak_waiting`, `idle`), `promoted_to` (string next stage or JSON null), `blocked_promotions` (array of `{target_stage, reason}` sorted by `target_stage`).

### pool_ledger.json

- `pools`: map keyed by `pool_id` sorted ascending. Each value: `effective_cap` (int), `artifacts_deferred` (int), `artifacts_promoted` (int), `max_promotions_per_day` (int base from file).

### stage_matrix.json

- `stages`: array sorted by ascending `target_stage`. Each object: `target_stage`, `artifacts_blocked` (int count of blocked rows citing this target), `artifacts_promoted` (int count of promotions to this target today).

### incident_journal.json

- `applied_events`: kept incidents in process order; each object includes `day`, `event_id`, `kind`, plus kind-specific fields (`artifact_id`, `pool_id`, `delta`, `start_day`, `end_day`) omitting absent ones. Keys sorted inside each object.

### summary.json

Sorted keys: `applied_incident_events`, `artifacts_total`, `deferred_artifacts`, `frozen_artifacts`, `idle_artifacts`, `ignored_incident_events`, `promoted_artifacts`, `promotions_today`, `quarantined_artifacts`, `soak_waiting_artifacts`.

Counts: `artifacts_total` is artifact file count; status counts partition artifacts; `promotions_today` equals count of non-null `promoted_to`; `ignored_incident_events` is original event count minus kept count.
