# Patch slot lattice audit (normative)

All inputs are UTF-8 JSON. The audit day is `pool_state.current_day` (integer). Never mutate anything under `/app/patch_slots/`.

## Hosts

Each file in `hosts/` is one object with `host_id`, `region`, `tier` (`production`, `staging`, or `development`), `applied_bundles` (array of bundle id strings), and `maintenance_windows` (array of inclusive `[start_day, end_day]` integer pairs).

## Bundles

Each file in `bundles/` is one object with `bundle_id`, `depends_on` (array of bundle id strings), `priority` (integer; lower values are more preferred when choosing at most one bundle to schedule today), and `reboot_minutes` (integer ≥ 0).

## Regions

Each file in `regions/` is one object with `region_id` and `max_hosts_per_day` (integer ≥ 0).

## Policy

`policy.json` contains `tier_rank` (map tier → integer; lower rank schedules earlier under capacity limits), `tier_calendar` (map tier → array of inclusive `[start_day, end_day]` pairs), and `reboot_budget_minutes_per_host` (integer ≥ 0).

## Effective maintenance window

For a host, build every inclusive interval `[max(h0, t0), min(h1, t1)]` where `[h0, h1]` is a host `maintenance_windows` entry and `[t0, t1]` is a `tier_calendar[tier]` entry. Discard intervals where `max > min`. The audit day is inside the window iff it lies in at least one surviving interval.

## Incidents

Read `incident_log.events`. Keep only events with `accepted == true` and `event.day <= current_day`. Sort kept events by ascending `(day, event_id)` and process in that order.

Supported `kind` values:

- `host_compromise`: requires `host_id`. From this event's `day` onward (inclusive), that host cannot schedule any bundle; its `host_status` is `quarantined`.
- `freeze_region`: requires `region_id`. From this event's `day` onward, every host in that region cannot schedule; `host_status` is `frozen_region`.
- `bundle_embargo`: requires `bundle_id`. Optional integer `start_day` (default `event.day`) and required integer `end_day`. On audit days `d` with `start_day <= d <= end_day`, the bundle is not a candidate for any host.
- `cap_bump`: requires `region_id` and integer `delta`. Add `delta` to that region's effective `max_hosts_per_day` for the capacity pass (additive across kept events).

Unknown kinds, malformed required fields, or `accepted` not true are ignored (not listed in the journal).

## Bundle candidacy (per host, before capacity)

A bundle is a candidate when:

1. It is not already listed in `applied_bundles`.
2. Every id in `depends_on` is present in `applied_bundles`.
3. The audit day lies in the host's effective maintenance window.
4. No kept `bundle_embargo` covers the audit day for this bundle id.
5. The host is not under an active `host_compromise` on the audit day.
6. The host's region is not under an active `freeze_region` on the audit day.

Among candidates, if any have `reboot_minutes` greater than `reboot_budget_minutes_per_host`, drop only those over-budget bundles. If none remain, the host has no schedulable bundle.

When at least one candidate remains, the chosen bundle is the candidate with the smallest `priority`; ties break by ascending ASCII `bundle_id`.

## Region capacity pass

Consider hosts that are not `quarantined` or `frozen_region` and that have a chosen bundle after the rules above. Sort those hosts by ascending `(tier_rank[tier], host_id)`.

Walk hosts in that order. For each host, let `R` be its region's base `max_hosts_per_day` plus the sum of `delta` from kept `cap_bump` events targeting `R`. If the count of hosts already assigned a bundle today in region `R` is strictly less than `R`, assign the chosen bundle (`host_status` `scheduled`). Otherwise the host is `deferred_capacity` and assigns no bundle today.

Hosts with no schedulable bundle and not quarantined/frozen are `idle`.

## Blocked candidate ledger

For every host, emit a `blocked_candidates` row for every bundle file id that is not in `applied_bundles` and was not scheduled today. Each row carries a single `reason`. Two of the seven reasons are host-scoped fates that override every per-bundle reason on that host; the remaining five are per-bundle conditions evaluated independently for each row.

Host-scoped reasons (apply to every row on the affected host, in strict precedence top-down):

| Reason | Condition |
|--------|-----------|
| `quarantine` | the host ended `quarantined` (active `host_compromise`) |
| `region_frozen` | the host ended `frozen_region` (active `freeze_region` on its region) |

If neither host-scoped reason applies, each row gets the single highest-precedence per-bundle reason from this list (top-down):

| Reason | Condition |
|--------|-----------|
| `capacity_deferred` | this row's bundle is the host's chosen candidate (per "Bundle candidacy" plus the priority/`bundle_id` tie-break) and the host ended `deferred_capacity` in the capacity pass |
| `embargoed` | a kept `bundle_embargo` covers the audit day for this row's `bundle_id` |
| `outside_window` | the audit day is outside the host's effective maintenance window |
| `missing_dependency` | some id in this row's bundle's `depends_on` is not in `applied_bundles` |
| `reboot_over_budget` | this row's bundle has `reboot_minutes` greater than `reboot_budget_minutes_per_host` while its `depends_on`, the effective window, and the embargo otherwise pass |

`capacity_deferred` therefore appears on **at most one row per host** — the bundle that would have been scheduled before the regional cap pushed the host into `deferred_capacity`. Every other unscheduled bundle on the same deferred host takes its reason from `embargoed` / `outside_window` / `missing_dependency` / `reboot_over_budget` per its own per-bundle conditions.

Within each host, sort the emitted rows by ascending ASCII `bundle_id`.

## Outputs (five files under `/app/audit/`)

Canonical JSON: UTF-8, two-space indent, ASCII only, object keys sorted lexicographically at every depth, colon plus single space, exactly one trailing newline at EOF.

### host_plan.json

- `hosts`: array sorted by ascending `host_id`. Each object: `host_id`, `region`, `tier`, `host_status` (`quarantined`, `frozen_region`, `deferred_capacity`, `scheduled`, `idle`), `scheduled_bundle` (string or JSON null), `blocked_candidates` (array of `{bundle_id, reason}` sorted by `bundle_id`).

### region_ledger.json

- `regions`: map keyed by `region_id` sorted ascending. Each value: `effective_cap` (int), `hosts_deferred` (int), `hosts_scheduled` (int), `max_hosts_per_day` (int base from file).

### bundle_matrix.json

- `bundles`: array sorted by ascending `bundle_id`. Each object: `bundle_id`, `hosts_blocked` (int count of blocked rows citing this bundle), `hosts_scheduled` (int count of hosts that scheduled this bundle today).

### incident_journal.json

- `applied_events`: kept incidents in process order; each object includes `day`, `event_id`, `kind`, plus kind-specific fields (`host_id`, `region_id`, `bundle_id`, `delta`, `start_day`, `end_day`) omitting absent ones. Keys sorted inside each object.

### summary.json

Sorted keys: `applied_incident_events`, `bundles_total`, `deferred_hosts`, `frozen_hosts`, `hosts_total`, `idle_hosts`, `ignored_incident_events`, `quarantined_hosts`, `scheduled_hosts`, `scheduled_bundles_today`.

Counts: `hosts_total` is host file count; `bundles_total` is bundle file count; status counts partition hosts; `scheduled_bundles_today` is count of non-null `scheduled_bundle`; `ignored_incident_events` is original event count minus kept count.
