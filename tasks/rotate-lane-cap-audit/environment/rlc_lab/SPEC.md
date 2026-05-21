# Rotating lane laboratory — normative specification

## Scope
All relative paths below live under `/app/rlc_lab/`. The audit reads this bundle only and writes exactly two files under `/app/audit/`: `lane_table.json` and `summary.json`.

## Required inputs
- `policy.json` — lane caps, floors, and mingle penalty.
- `pool_state.json` — integer field `current_day`.
- `anchors/a.json` and `anchors/b.json` — each contains JSON array `items` listing `item_id` strings whose **final per-item allocations after lane caps** contribute to that region total.
- `ancillary/x.json`, `ancillary/y.json`, `ancillary/z.json`, `ancillary/w.json` — auxiliary packaging; only `x.json` affects the summary note.
- `incident_log.json` — ordered replay list under field `events`.
- `items/item_XX.json` for `XX` from `00` to `11` inclusive — zero-padded two digits.

## policy.json fields
- `active_regions` — array of region labels. Items whose `region` is not listed here are ignored before incident replay and never return.
- `lanes` — object mapping `lane_id` strings to `{ "members": [ ... item_id strings ... ], "cap": <int> }`. Fixture data guarantees every item whose `region` is listed in `active_regions` has its `item_id` in exactly one lane `members` list before any replay begins.
- `lane_floor` — non-negative integer floor applied per item after rotation to bound the L1 magnitude.
- `mingle_penalty` — non-negative integer subtracted from a lane's summed raw contributions when that lane still contains items with at least two distinct `tier` strings after replay.

## Item record fields
Each item file is one object with:
- `item_id` — stable identifier string matching `policy.lanes.*.members` entries.
- `region` — one of `a`, `b`, or `none`.
- `tier` — string tier label used for mingle detection.
- `born_day` — integer day counter.
- `rotate_period_days` — positive integer period controlling rotation cadence.
- `x` and `y` — signed integers representing the planar vector before rotation.

## Integer rotation and L1 contribution
Let `D` be `pool_state.current_day`. For each surviving item, define `B = born_day`, `P = rotate_period_days`. If `D < B`, set `k = 0`. Otherwise set `k = ((D - B) // P) % 4`. Starting from `(xr, yr) = (x, y)`, apply the rotation operator exactly `k` times: each operator application maps `(xr, yr)` to `(-yr, xr)`. The contribution is `max(lane_floor, abs(xr) + abs(yr))`.

## Incident replay
Read `incident_log.events` in array order without sorting. Let `applied_events` equal the number of objects processed. Each object has string field `kind`. Unknown kinds are ignored for state but still counted in `applied_events`.

1. `tier_period_bump` — fields `tier` (string) and `add` (integer, may be negative). For every surviving item whose `tier` matches, replace `rotate_period_days` with `max(1, rotate_period_days + add)`.
2. `lane_cap_rescale` — fields `lane_id` (string) and `new_cap` (integer). If `lane_id` exists in `policy.lanes`, replace its `cap` with `new_cap`.
3. `item_excise` — field `item_id` (string). Remove the item with that identifier from the working set.

Filtering to `active_regions` happens **before** any incident replay. Removed items never return.

## Lane sums and mingle adjustment
For each lane in ascending `lane_id` string order, compute `S_raw` as the sum of contributions of its surviving members (missing members contribute `0`). If among those members with positive contribution there exist at least two different `tier` strings, replace `S_raw` with `max(0, S_raw - mingle_penalty)`; call this `S_adj`. Otherwise `S_adj = S_raw`.

Let `cap` be the lane's current cap. If `S_adj <= cap`, set `scaled = false` and `target = S_adj`. If `S_adj > cap`, set `scaled = true` and `target = cap`. Record `pre_cap_sum = S_adj` and `post_cap_sum = target`.

### Integer allocation to items within a lane
Let `numer = target` and `denom = S_raw` where `S_raw` is the **pre-mingle** sum for that lane (still the sum of raw contributions before subtracting `mingle_penalty`). If `denom == 0`, every member receives allocation `0`. Otherwise for each `item_id` in the lane's `members` array in file order, start with `alloc[id] = floor(contrib[id] * numer / denom)` where `contrib[id]` is the item's raw contribution (zero if missing). Then compute `slack = numer - sum(alloc)`. If `slack > 0`, repeatedly add `1` to `alloc[id]` by visiting member ids with positive `contrib[id]` in ascending `item_id` string order in a cyclic pass until `slack` reaches zero.

## Region totals
Start from zero for each label in `active_regions`. For each region label `r`, sum the final allocations for every `item_id` listed in `anchors/r.json.items` that still exists in the working set after replay. Then subtract integer field `ambient_subtract` read from `ancillary/x.json` independently for each region (default `0` if absent or not an int) and clamp at zero.

## summary.json fields
- `current_day` — copy `D`.
- `applied_events` — processed incident count.
- `regions` — object with one integer field per label in `active_regions` in ascending key order.
- `ancillary_note` — string from `ancillary/x.json["note"]` if present, else empty string.

## lane_table.json fields
- `lanes` — array, one object per lane in ascending `lane_id`, each with `lane_id`, `pre_cap_sum`, `post_cap_sum`, `scaled` (boolean), `mingled` (boolean, true iff the mingle penalty actually changed the summed raw total for that lane).

## On-disk JSON encoding
Write UTF-8 JSON with `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` and end each file with a single trailing newline character.
