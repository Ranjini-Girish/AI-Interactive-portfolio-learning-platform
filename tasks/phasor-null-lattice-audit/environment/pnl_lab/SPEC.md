# Phasor null lattice audit

This document is normative for every field, ordering rule, and numeric rounding contract referenced by the task prompt. All JSON on disk is UTF-8. Strings are ASCII-only. Output objects must use exactly the listed keys; omit keys with no legal value unless the schema explicitly allows an empty list.

## Input layout under `/app/pnl_lab/`

Read `policy.json`, `pool_state.json`, `domain_layout.json`, `incident_log.json`, `anchors/a.json`, `anchors/b.json`, every `items/item_*.json` file (lexicographic filename order defines processing order for records), and both `ancillary/*.json` files for human context only. Ancillary JSON never changes the math.

`policy.json` fields:

- `bin_ring` (positive int): ring size `R`. Every item’s active bin is `((bin_index % R) + R) % R`.
- `wrap_delta` (non-negative int): bins `i` and `j` are directly coupled when circular distance `min((i-j) mod R, (j-i) mod R)` is `<= wrap_delta`. Build an undirected graph whose vertices are bins `0..R-1` and whose edges are every coupled pair `i<j`. Connected components are merged bins.
- `amp_floor` (non-negative float): lower bound on per-item effective magnitude after scaling.
- `deep_null_lt` and `soft_null_lt` (positive floats with `deep_null_lt < soft_null_lt`): phasor magnitude thresholds defined below.
- `audit_day` (int): only incident events with `day <= audit_day` apply.
- `default_region` (string): region id used when no layout prefix matches.

`pool_state.json` supplies baseline `drain` map tier name to float in `[0,1]`.

`domain_layout.json` holds `regions` array objects with `id` and `path_prefix`. When matching an item’s `region_path`, consider every region whose `path_prefix` is a literal prefix of `region_path`. If none match, use `default_region`. If several match, pick the one with the longest `path_prefix`; ties break by ascending `id`.

Anchor scales multiply. Let `A(r)` read from `anchors/a.json` `scales` map with default `1.0` when a key is absent. Let `B(r)` read similarly from `anchors/b.json`. The anchor product is `A(r)*B(r)` for the resolved region id `r`.

Incident events share shape `{ "day": int, "kind": string, "payload": object }`. Consider only events with `day <= audit_day`, sort by ascending `day`, then by ascending original array index. Apply in that order:

- `suppress_items`: payload `{ "item_ids": [string, ...] }` adds ids to a suppressed set for the remainder of the replay.
- `quarantine_lineage`: payload `{ "lineage": string }` adds the lineage token to a quarantine set for the remainder.
- `tier_drain`: payload `{ "tiers": { tier: float, ... } }` replaces the active drain entry for each listed tier with the provided float, clamping each stored drain to `[0,1]`.

Effective magnitude for an item that is not suppressed and whose lineage is not quarantined:

1. Resolve region `r` from `region_path`.
2. Let `d` be the active drain for `tier`, default `0` when missing, clamp to `[0,1]`.
3. Let `m0 = magnitude * anchor_product(r) * (1 - d)`.
4. Effective `m = m0` if `m0 >= amp_floor`, otherwise `m = amp_floor`.
5. Convert `phase_deg` to radians using `theta = ((phase_deg mod 360)+360) mod 360` degrees, then `theta_rad = theta * pi / 180`.
6. Phasor contribution is `(m * cos(theta_rad), m * sin(theta_rad))`.

Items that are suppressed or whose lineage is quarantined are excluded from phasor sums but still appear in membership lists described below.

## Outputs under `/app/audit/`

Write exactly three files: `bin_graph.json`, `null_manifest.json`, `summary.json`. Each file is a single JSON object, ends with one newline, and uses canonical serialization: recursively sorted object keys, two-byte comma plus colon separators (no extra spaces), numbers rounded with `round` to six fractional digits, `-0` must never appear (use `0`), arrays preserve the order mandated below (arrays are not sorted).

### `bin_graph.json`

Keys: `bin_ring` (int `R`), `edges` (array). Emit every undirected bin pair `0 <= bin_lo < bin_hi < R` where both bins share a connected component under the coupling rule **and** their circular distance is `<= wrap_delta`. Each edge object keys `bin_lo` then `bin_hi` sorted ascending inside the object. Sort the `edges` array lexicographically by `(bin_lo, bin_hi)`.

### `null_manifest.json`

Key `components`: array of one object per connected bin component, sorted by ascending `anchor_bin`, then ascending `root_bin` where `root_bin` is the disjoint-set representative after unions processed in increasing bin index order (always union the larger-index root into the smaller-index root). Fields per component:

- `anchor_bin`: smallest bin index in the component.
- `bins`: sorted list of bin integers in the component.
- `root_bin`: representative described above.
- `contributors`: sorted ids of items in those bins that are neither suppressed nor quarantined by lineage.
- `suppressed_ids`: sorted ids of suppressed items whose normalized bin lies in the component (may be empty).
- `phasor`: object with keys `im` then `re` in that key order each rounded as above. If there are no contributors, both are `0`.
- `rms_mag`: `hypot(re, im)` rounded; `0` when vacant.
- `class`: `vacant` when there are zero contributors. Otherwise compare `rms_mag` to thresholds: `deep_null` when `rms_mag < deep_null_lt`, else `soft_null` when `rms_mag < soft_null_lt`, else `energized`.

### `summary.json`

Include at least: `audit_day`, `bin_ring`, `wrap_delta`, `items_total` (count of item files processed), `unique_contributors` (distinct contributor ids counted once across the whole run), `suppressed_items` (size of suppressed set), `quarantined_lineages` (size of quarantine set), `components_total`, `components_vacant`, `deep_null_components`, `soft_null_components`, `components_energized` counting `class` values across components.

All counts are JSON numbers without trailing junk fields.
