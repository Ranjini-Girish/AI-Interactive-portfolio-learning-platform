# Heat flux yoke laboratory — normative specification

## Scope
All relative paths below live under `/app/hfy_lab/`. The audit reads this bundle only and writes exactly two files under `/app/audit/`: `yoke_table.json` and `summary.json`. Do not assume any other filenames exist.

## Required inputs
- `policy.json` — laboratory policy.
- `pool_state.json` — contains integer `current_day`.
- `anchors/a.json` and `anchors/b.json` — each contains a JSON array field `cells` listing cell identifiers observed for that region label.
- `ancillary/x.json` — auxiliary note fields used only by the summary output.
- `incident_log.json` — ordered replay list under field `events`.
- `items/item_XX.json` for `XX` from `00` to `17` inclusive — zero-padded two digits.

## policy.json fields
- `active_regions` — array of region labels. The audit only considers items whose `region` string is an element of this array. Items tagged `none` are always ignored and never participate in span detection.
- `yokes` — object mapping `yoke_id` strings to objects `{ "cells": [ ... ], "flux_cap": <int> }`. Each `cells` array lists participating cells. Fixture data guarantees every item’s `cell` appears in exactly one yoke’s `cells` list.
- `flux_floor_mw` — non-negative integer floor applied per item after decay.
- `span_penalty_permille` — integer in `0..1000`. When a yoke still contains at least one surviving item tagged `a` and at least one surviving item tagged `b` after filtering, that yoke is called **spanned** for cap math.

## Item record fields
Each `items/item_XX.json` file is one object with:
- `item_id` — stable string identifier.
- `cell` — cell identifier string.
- `yoke_id` — string referencing `policy.yokes`.
- `region` — one of `a`, `b`, or `none`.
- `tier` — string tier label used by incidents.
- `born_day` — integer day counter.
- `flux0_mw` — non-negative integer baseline milliwatts.
- `k_mw_per_day` — non-negative integer linear decay slope in milliwatts per day.

## Linear decay
Let `D` be `pool_state.current_day`. For each item that survived filtering and later removals, define `age = max(0, D - born_day)` and `raw_item = max(flux_floor_mw, flux0_mw - k_mw_per_day * age)`.

## Incident replay
Read `incident_log.events` in array order without sorting. Let `applied_events` equal the number of objects processed. Each object has string field `kind`. Unknown kinds are ignored but still counted in `applied_events`.

1. `tier_k_boost` — fields `tier` (string) and `add` (integer, may be negative). For every item still present, if `tier` matches, increase `k_mw_per_day` by `add` (clamp at zero after each event).
2. `yoke_cap_rescale` — fields `yoke_id` and `new_cap` (integer). If `yoke_id` exists in `policy.yokes`, replace its `flux_cap` with `new_cap` (ignore if missing).
3. `cell_excise` — field `cell` (string). Remove every item whose `cell` equals that value.

Filtering to `active_regions` happens **before** any incident replay. Removed items never return.

## Cell totals
After replay, compute `cell_raw[cell]` as the sum of `raw_item` for surviving items in that cell.

## Yoke aggregation and caps
Process yokes in ascending `yoke_id` string order. For each yoke:
- Let `S_raw` be the sum of `cell_raw[c]` for every `c` listed in that yoke’s `cells` array (missing or zero cells contribute `0`).
- Let `spanned` be true iff, among surviving items that belong to this yoke’s cell list, there exists at least one item tagged `a` and at least one item tagged `b`. Items with `region` equal to `none` never participate in span detection.
- Define `S_pen = floor(S_raw * span_penalty_permille / 1000)` when `spanned` is true; otherwise `S_pen = S_raw`.
- Let `cap` be the yoke’s current `flux_cap`. If `S_pen <= cap`, set `scaled = false` and `target = S_pen`. If `S_pen > cap`, set `scaled = true` and `target = cap`.
- Record `pre_cap_sum = S_pen` and `post_cap_sum = target`.

### Integer allocation to cells
Let `numer = target` and `denom = S_raw`. If `denom == 0`, every cell in the yoke receives allocation `0`. Otherwise, for each cell `c` in the yoke list in file order, start with `alloc[c] = floor(cell_raw[c] * numer / denom)`. Then compute `slack = numer - sum(alloc)` over those cells. If `slack > 0`, add `1` to `alloc[c]` by visiting cells with positive `cell_raw[c]` in ascending `cell` string order, repeating that ordered pass until `slack` reaches zero (this is the largest-remainder tie schedule).

These per-cell allocations are the values used by the region totals below.

## Region totals
Start from zero for each label in `active_regions`. For each region label `r`, sum the final per-cell allocations for every cell that appears both in `anchors/r.json.cells` and participates in any yoke for this audit. After that, read integer `ambient_subtract` from `ancillary/x.json` (default `0` if absent or not an int). Subtract `ambient_subtract` independently from each region total, then clamp at zero.

## summary.json fields
- `current_day` — copy `D`.
- `applied_events` — processed incident count.
- `regions` — object with one integer field per label in `active_regions` in ascending key order.
- `ancillary_note` — string from `ancillary/x.json["note"]` if present, else empty string.

## yoke_table.json fields
- `yokes` — array, one object per yoke in ascending `yoke_id`, each with `yoke_id`, `pre_cap_sum`, `post_cap_sum`, `scaled` (boolean), `spanned` (boolean).

## On-disk JSON encoding
Write UTF-8 JSON with `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` and end each file with a single trailing newline character.
