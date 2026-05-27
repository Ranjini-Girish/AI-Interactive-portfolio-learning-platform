# Tier quota rollup

Normative contract for `/app/audit/allocations.json` and `/app/audit/summary.json`. Read `policy.json`, `events.json`, and every `items/*.json` under this directory. Integer division truncates toward zero.

## Inputs

- `policy.json`: `audit_day` (int), `tier_order` (array, first is highest priority), `tier_caps` (object tier string to int capacity).
- Each item file: `item_id`, `tier`, `demand` (int >= 0).
- `events.json`: `tier_derates` (optional array) and `item_freezes` (optional array). Ignore unknown fields.

## Tier derates

For each derate with `start_day <= audit_day <= end_day`, multiply that tier cap by `factor_bp / 10000` (floor to int). Multiple derates on one tier multiply in array order.

## Item freezes

For each freeze with `start_day <= audit_day <= end_day`, the item is frozen: `allocated` is 0, `status` is `frozen`, demand is still recorded.

## Processing order

Sort items by tier rank using `tier_order` index (unlisted tiers sort after listed tiers, tie-break ascending tier string), then ascending `item_id`.

## Allocation

Maintain `tier_remaining` from effective caps. For each non-frozen item, `allocated = min(demand, tier_remaining[tier])`, then subtract from `tier_remaining`. Status `ok` when `allocated == demand`, else `shortfall`.

## allocations.json

Top-level key `items`: array sorted by processing order. Each object: `item_id`, `tier`, `status`, `demand`, `allocated`.

## summary.json

Fields: `audit_day`, `items_processed` (count of item files), `frozen_items` (count frozen), `status_counts` with keys `frozen`, `ok`, `shortfall` (each int), `tiers_touched` (sorted list of tiers with any strictly positive allocation).

## Canonical JSON

UTF-8, indent 2, sorted keys recursively, ASCII-only, single trailing newline after the closing brace.
