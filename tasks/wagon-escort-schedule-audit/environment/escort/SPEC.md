# Wagon escort schedule audit (normative)

All inputs are UTF-8 JSON unless noted. The planning day is `pool_state.current_day` (integer). Never mutate anything under `/app/escort/`.

## Routes and depots

Each route file `routes/<route_id>.json` contains `route_id`, `depot_ids` (array of depot id strings), and `segments` (array of objects with `segment_id` and integer `base_hazard`). Segments are summed in file order.

Each depot file `depots/<depot_id>.json` contains `depot_id` and integer `active_until` (inclusive last operative day).

## Convoys and guards

Convoy files `convoys/<convoy_id>.json` contain `convoy_id`, `tier` in {`gold`,`silver`,`bronze`}, integer `departure_day`, string `route_id`, and integer `required_guards` (≥ 0).

Guard files `guards/<guard_id>.json` contain `guard_id` and integer `skill` (higher is better).

## Incidents

Read `incident_log.events`. Keep only events with `accepted == true` and `day <= current_day`. Sort kept events by ascending `(day, event_id)` and apply in that order.

Supported kinds (others ignored):

- `hazard_spike`: requires `route_id` and integer `delta`. Adds `delta` to every segment `base_hazard` on that route for all later hazard work (cumulative across events).
- `depot_closure`: requires `depot_id` and integer `effective_day`. Sets the depot operative limit to `min(prior operative limit, effective_day - 1)` for all later work (cumulative min).
- `guard_bench`: requires `guard_id`. That guard is unavailable for assignment for the rest of the run.
- `route_embargo`: requires `route_ids` (array of route id strings). Cross-cutting override described below.

Malformed events (missing required fields, wrong types) are ignored like unsupported kinds.

## Hazard and risk (per convoy)

Let `raw` be the sum of effective segment hazards on the convoy route after all applied `hazard_spike` adjustments.

Subtract once: `raw = max(0, raw - policy.hazard_decay_by_tier[tier])`.

Depot coverage: the convoy is **covered** iff at least one `depot_id` listed on its route has operative limit `>= convoy.departure_day` after depot_closure adjustments.

If uncovered, multiply: `raw = (raw * policy.uncovered_multiplier_pct_by_tier[tier]) // 100` (integer floor division).

Thresholds come from `policy.risk_thresholds_by_tier[tier]` with integer fields `medium`, `high`, `critical`. Classify:

- `low` if `raw < medium`
- `medium` if `medium <= raw < high`
- `high` if `high <= raw < critical`
- `critical` if `raw >= critical`

Collect `reasons` (unique, ASCII-sorted): include `uncovered_route` when uncovered; include `hazard_spike_active` when any kept `hazard_spike` touched this convoy route; include `route_embargo` when this convoy's route is listed on any kept `route_embargo`.

**Embargo override:** when a convoy route appears on any kept `route_embargo.route_ids`, its final `risk_level` must be at least `high` (promote lower bands to `high`), `route_embargo` must appear in `reasons`, and assignment uses the embargo branch below.

## Guard assignment

Process convoys in ascending `(departure_day, convoy_id)` order.

Eligible guards: not benched by a kept `guard_bench`, sorted by descending `skill` then ascending `guard_id`.

`policy.guard_cooldown_days` is integer `C`. When considering guard `g` for convoy `c` departing day `D`, reject `g` if `g` was already assigned to a different convoy departing day `D0` with `abs(D - D0) <= C`.

When a convoy route is embargoed, emit `assigned_guard_ids: []` and `assignment_status: blocked_escort` regardless of guard availability.

Otherwise greedily pick up to `required_guards` eligible guards passing cooldown. Status:

- `assigned` if count equals `required_guards` and `required_guards > 0`
- `partial` if `0 < count < required_guards`
- `unassigned` if `required_guards == 0` OR count is 0

Record each chosen guard last-use day as this convoy departure day.

## Route verdict (per route referenced by any convoy)

For each distinct `route_id` appearing in convoy inputs, emit one verdict object.

Base verdict from max convoy `risk_level` on that route among convoys with `departure_day <= current_day`, using precedence `critical > high > medium > low`.

If the route is listed on any kept `route_embargo`: verdict `blocked` with `reasons` containing `route_embargo`.

Else if max risk is `critical`: `blocked` with `reasons` containing `critical_risk`.

Else if max risk is `high`: `diverted` with `reasons` containing `high_risk`.

Else: `cleared` with empty `reasons`.

When multiple reasons apply, sort unique strings ASCII ascending.

## Outputs (five files under `/app/schedule/`)

Canonical JSON: UTF-8, two-space indent, ASCII only, object keys sorted lexicographically at every depth, colon plus single space, exactly one trailing newline at EOF.

### convoy_risk.json

`convoys`: array sorted by `convoy_id` ascending. Each object: `convoy_id`, `departure_day`, `raw_hazard` (int), `risk_level`, `reasons` (sorted unique strings), `route_id`, `tier`.

### guard_assignments.json

`convoys`: array sorted by `convoy_id` ascending. Each object: `assigned_guard_ids` (sorted ascending), `assignment_status`, `convoy_id`, `required_guards`.

### route_verdict.json

`routes`: array sorted by `route_id` ascending. Each object: `reasons`, `route_id`, `verdict` in {`cleared`,`diverted`,`blocked`}.

### incident_journal.json

`applied_events`: array in process order `(day asc, event_id asc)`. Each element includes `day`, `event_id`, `kind`, plus kind-specific fields when present (`delta`, `depot_id`, `effective_day`, `guard_id`, `route_id`). Omit absent optional fields. Keys sorted inside each object.

### summary.json

Fields (sorted keys): `applied_incident_events` (int), `blocked_routes` (int), `convoys_total` (int), `covered_convoys` (int), `embargo_routes` (int), `fully_assigned_convoys` (int), `ignored_incident_events` (int), `route_embargo_active` (bool), `uncovered_convoys` (int).

Counts: `convoys_total` is convoy file count. `covered_convoys` counts convoys that were depot-covered. `uncovered_convoys` is total minus covered. `fully_assigned_convoys` counts `assignment_status == assigned`. `blocked_routes` counts route verdict `blocked`. `route_embargo_active` true iff any kept route_embargo. `embargo_routes` counts distinct routes named on kept embargo events. `applied_incident_events` is journal length. `ignored_incident_events` is original event count minus kept count.
