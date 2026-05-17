# Export batch window audit (normative)

All inputs are UTF-8 JSON. The audit day is `pool_state.current_day` (integer). Never mutate anything under `/app/export_batches/`.

## Sources

Each file in `sources/` is one object with `source_id`, `warehouse_id`, `tier` (`production`, `staging`, or `development`), `exported_batches` (array of batch id strings already exported), and `sync_windows` (array of inclusive `[start_day, end_day]` integer pairs).

## Batches

Each file in `batches/` is one object with `batch_id`, `depends_on` (array of batch id strings), `priority` (integer; lower values are more preferred when choosing at most one batch to schedule today), and `credit_cost` (integer ≥ 0).

## Warehouses

Each file in `warehouses/` is one object with `warehouse_id`, `export_credits` (integer ≥ 0 shared pool for the audit day), and `max_exports_per_day` (integer ≥ 0).

## Policy

`policy.json` contains `tier_rank` (map tier → integer; lower rank schedules earlier under capacity limits), `tier_calendar` (map tier → array of inclusive `[start_day, end_day]` pairs), and `max_credit_cost_per_source` (map tier → integer; a batch whose `credit_cost` exceeds this ceiling is not a candidate for sources of that tier).

## Effective sync window

For a source, build every inclusive interval `[max(s0, t0), min(s1, t1)]` where `[s0, s1]` is a source `sync_windows` entry and `[t0, t1]` is a `tier_calendar[tier]` entry. Discard intervals where `max > min`. The audit day is inside the window iff it lies in at least one surviving interval.

## Incidents

Read `incident_log.events`. Keep only events with `accepted == true` and `event.day <= current_day`. Sort kept events by ascending `(day, event_id)` and process in that order.

Supported `kind` values:

- `source_compromise`: requires `source_id`. When `event.day <= current_day`, that source cannot schedule any batch; its `source_status` is `quarantined`.
- `freeze_warehouse`: requires `warehouse_id`. When `event.day <= current_day`, every source in that warehouse cannot schedule; `source_status` is `warehouse_frozen`.
- `batch_embargo`: requires `batch_id`. Optional integer `start_day` (default `event.day`) and required integer `end_day`. On audit days `d` with `start_day <= d <= end_day`, the batch is not a candidate for any source.
- `cap_bump`: requires `warehouse_id` and integer `delta`. Add `delta` to that warehouse's effective `max_exports_per_day` for the capacity pass (additive across kept events).
- `credit_grant`: requires `warehouse_id` and integer `delta`. Add `delta` to that warehouse's starting `export_credits` pool before the credit pass (additive across kept events).

Unknown kinds, malformed required fields, or `accepted` not true are ignored (not listed in the journal). Events with `day > current_day` are also ignored.

## Batch candidacy (per source, before capacity)

A batch is a candidate when:

1. It is not already listed in `exported_batches`.
2. Every id in `depends_on` is present in `exported_batches`.
3. The audit day lies in the source's effective sync window.
4. No kept `batch_embargo` covers the audit day for this batch id.
5. The source is not under an active `source_compromise` on the audit day.
6. The source's warehouse is not under an active `freeze_warehouse` on the audit day.
7. `credit_cost` is not greater than `max_credit_cost_per_source[tier]`.

When at least one candidate remains, the chosen batch is the candidate with the smallest `priority`; ties break by ascending ASCII `batch_id`.

## Warehouse capacity and credit pass

Consider sources that are not `quarantined` or `warehouse_frozen` and that have a chosen batch after the rules above. Sort those sources by ascending `(tier_rank[tier], source_id)`.

Walk sources in that order. For each source, let `W` be its warehouse. Let `effective_cap` be that warehouse's base `max_exports_per_day` plus the sum of `delta` from kept `cap_bump` events targeting `W`. Let `export_credits_start` be the warehouse file's `export_credits` plus the sum of `delta` from kept `credit_grant` events targeting `W`, minus credits already debited earlier in this pass.

If the count of sources already assigned a batch today in warehouse `W` is greater than or equal to `effective_cap`, the source is `deferred_capacity`, assigns no batch today, and the blocked row for its chosen batch must cite `capacity_deferred`.

Otherwise, if `export_credits_remaining` for `W` is strictly less than the chosen batch's `credit_cost`, the source is `credit_deferred`, assigns no batch today, and the blocked row for its chosen batch must cite `credit_deferred`.

Otherwise debit the batch's `credit_cost` from `export_credits_remaining`, increment that warehouse's scheduled count, and set `source_status` `scheduled` with `scheduled_batch` equal to the chosen batch id.

Sources with no schedulable batch and not quarantined or warehouse-frozen are `idle`.

## Blocked candidate ledger

For every source, for every batch file id that is not in `exported_batches` and was not scheduled today, emit one `blocked_candidates` row with the single highest-precedence reason among:

| Reason | Condition |
|--------|-----------|
| `quarantine` | active compromise on source |
| `warehouse_frozen` | active freeze on source warehouse |
| `capacity_deferred` | source ended `deferred_capacity` for this batch |
| `credit_deferred` | source ended `credit_deferred` for this batch |
| `embargoed` | embargo covers audit day |
| `outside_window` | audit day outside effective sync window |
| `missing_dependency` | some `depends_on` not exported |
| `credit_over_budget` | batch `credit_cost` exceeds tier ceiling while dependencies/window/embargo otherwise pass |

Precedence order above is strict (top wins). Sort rows by ascending `batch_id`. Use an empty array when there are no pending batches.

## Outputs (five files under `/app/audit/`)

Canonical JSON: UTF-8, two-space indent, ASCII only, object keys sorted lexicographically at every object depth, colon plus single space, exactly one trailing newline at EOF.

### source_plan.json

- `sources`: array sorted by ascending `source_id`. Each object: `blocked_candidates` (array of `{batch_id, reason}` sorted by `batch_id`), `scheduled_batch` (string or JSON null), `source_id`, `source_status` (`quarantined`, `warehouse_frozen`, `deferred_capacity`, `credit_deferred`, `scheduled`, `idle`), `tier`, `warehouse_id`.

### warehouse_ledger.json

- `warehouses`: map keyed by `warehouse_id` sorted ascending. Each value: `effective_cap` (int), `export_credits_remaining` (int after debits), `export_credits_start` (int before debits), `max_exports_per_day` (int base from file), `sources_deferred_capacity` (int), `sources_deferred_credit` (int), `sources_scheduled` (int).

### batch_matrix.json

- `batches`: array sorted by ascending `batch_id`. Each object: `batch_id`, `sources_blocked` (int count of blocked rows citing this batch), `sources_scheduled` (int count of sources that scheduled this batch today).

### incident_journal.json

- `applied_events`: kept incidents in process order; each object includes `day`, `event_id`, `kind`, plus kind-specific fields (`source_id`, `warehouse_id`, `batch_id`, `delta`, `start_day`, `end_day`) omitting absent ones. Keys sorted lexicographically inside each object.

### summary.json

Sorted keys: `applied_incident_events`, `batches_total`, `credit_deferred_sources`, `deferred_sources`, `frozen_sources`, `idle_sources`, `ignored_incident_events`, `quarantined_sources`, `scheduled_batches_today`, `scheduled_sources`, `sources_total`.

Counts: `sources_total` is source file count; `batches_total` is batch file count; `quarantined_sources`, `frozen_sources`, `deferred_sources`, `credit_deferred_sources`, `scheduled_sources`, and `idle_sources` partition sources by final `source_status`; `scheduled_batches_today` is count of non-null `scheduled_batch`; `ignored_incident_events` is original event count minus kept count.
