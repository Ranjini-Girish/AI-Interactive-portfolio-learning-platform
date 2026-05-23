# Infer blend quota audit

Normative rules for `/app/audit/allocations.json`, `/app/audit/pool_usage.json`, and `/app/audit/summary.json`. Read `policy.json`, `incidents.json`, every `pools/*.json`, and every `routes/*.json` under this directory. Integer division truncates toward zero. Basis points use 10000 = 100 percent.

## Inputs

- `policy.json` fields: `allocation_day` (int), `tier_priority` (array of tier strings, first is highest), `shared_groups` (array of `{group_id, cap_units}`). Ignore unknown fields.
- Each pool file: `pool_id` (string), `capacity_units` (int ≥ 0), optional `share_group` (string referencing a `shared_groups.group_id`).
- Each route file: `route_id`, `tier`, `forecast_units` (int >= 0), `primary_share_bp` (int 0..10000 inclusive), `primary_pool`, `canary_pool` (pool ids), optional `shadow_canary` (bool, default false). Ignore unknown fields.
- `incidents.json` has `events`, each with `kind`, `accepted` (bool), plus kind-specific keys.

## Incident semantics

Only events with `accepted == true` apply. Days are inclusive integer ranges.

- `pool_derate`: `pool_id`, `factor_bp` (int 1..10000), `start_day`, `end_day`. When `allocation_day` is within the inclusive range, the pool baseline `capacity_units` is multiplied by `factor_bp / 10000` and floored to an integer effective capacity. Multiple derates on the same pool multiply in file order (later events apply after earlier ones).
- `route_freeze`: `route_id`, `start_day`, `end_day`. When active on `allocation_day`, the route is frozen (see Frozen routes).

## Tier ordering

Route processing order: lower numeric rank first, using `tier_priority` index (0 = highest). Tiers not listed sort after listed tiers in ascending lexicographic tier string order. Tie-break: ascending `route_id`.

## Demands

For a non-frozen route: `primary_requested = (forecast_units * primary_share_bp) / 10000`, `canary_requested = forecast_units - primary_requested`. Frozen routes force both requested values to 0.

## Allocation pass

Process routes in the tier order above. Maintain `pool_remaining[pool_id]` from effective pool capacities after derates. Maintain `group_remaining[group_id]` initialized from `shared_groups.cap_units` when the group exists; if a pool has no `share_group`, only its own `pool_remaining` binds.

For each non-frozen route, allocate primary first, then canary:

1. Primary draw `want_p = primary_requested`. The route may take `min(want_p, pool_remaining[primary_pool])`. If the primary pool has `share_group`, the draw is further limited by `group_remaining[share_group]`. The actual draw is the minimum of these caps. Subtract from `pool_remaining` for the primary pool and from `group_remaining` when applicable.
2. Canary draw `want_c = canary_requested`. If `shadow_canary` is true, the canary draw is 0 and neither pool nor group ledgers for canary are changed. Otherwise apply the same min-cap logic against `canary_pool` (and its `share_group` if present).

Frozen routes: emit status `frozen`, both allocated fields 0, both requested 0, empty `reasons`.

## Route status and reasons

For non-frozen routes, compare requested versus allocated per side (shadow only affects canary allocation, not `canary_requested`):

- If both sides have shortfall: status `both_shortfall`.
- Else if only primary short: `primary_shortfall`.
- Else if only canary short: `canary_shortfall`.
- Else: `ok`.

`reasons` is a sorted unique list of short strings:

- `primary_pool_exhausted` when primary shortfall.
- `canary_pool_exhausted` when canary shortfall and not shadow.
- `shared_group_exhausted` when any draw was strictly limited by a group cap (even if the limiting side was not the one that ended short, include once if any draw in that route hit the group cap as the binding min). When `pool_remaining` and `group_remaining` are both binding minimums for the same draw—including when both reach zero on that draw—still include this reason whenever the group cap was one of the minimums used to compute the actual draw.

If none apply, `reasons` is `[]`.

## Output shapes

### allocations.json

Top-level key `routes`: array sorted ascending by `route_id`. Each object keys: `route_id`, `tier`, `status`, `shadow_canary`, `primary_requested`, `primary_allocated`, `canary_requested`, `canary_allocated`, `reasons` (array of strings, sorted ascending).

### pool_usage.json

- `pools`: one object per pool that appears in any route’s `primary_pool` or `canary_pool`, or any pool file present under `pools/`. Sort ascending by `pool_id`. Fields: `pool_id`, `capacity_effective` (after derates), `remaining_units` (after all allocations), `primary_drawn`, `canary_drawn` (sums across routes, shadow canary draws count 0 toward canary_drawn).
- `shared_groups`: one object per policy group, sorted by `group_id`. Fields: `group_id`, `cap_units`, `remaining_units` after all draws that counted against the group.

### summary.json

Fields: `allocation_day`, `routes_processed` (count of route files), `frozen_routes`, `status_counts` (object with exactly the keys `ok`, `frozen`, `primary_shortfall`, `canary_shortfall`, `both_shortfall` in ascending key order, each an int count), `pools_touched` (sorted list of pool ids that had any strictly positive draw), `groups_binding` (sorted list of `group_id` that were the binding minimum for at least one primary or non-shadow canary draw on some route).

## Canonical JSON

Write UTF-8 JSON with `indent=2`, two-space indent, `, ` separators after colons and commas, sorted object keys recursively at every object, ASCII-only content, and a single trailing newline after the closing brace.
