# Intermodulation headroom lab (normative)

All JSON consumed and emitted by the audit is UTF-8. On-disk audit files use JSON with ASCII-only text, two-space indentation, sorted object keys at every object depth, and a single trailing newline after the closing value. Arrays must be sorted as specified even when the natural scan order differs.

## Inputs

Let `LAB_ROOT` be the absolute path in environment variable `IMHA_DATA_DIR` when that variable is set to a non-empty string, otherwise `/app/imhr_lab`.

Read `LAB_ROOT/policy.json`, `LAB_ROOT/pool_state.json`, `LAB_ROOT/incident_log.json`, `LAB_ROOT/anchors/window.json`, and every `LAB_ROOT/sites/*.json` file. Ignore `LAB_ROOT/ancillary/` for computations; it is packaging metadata only.

Each site file contains string `site_id`, string `tier` (`gold`, `silver`, or `bronze`), string `band_tag` (members of `pool_state.band_process_order`), and integer array `emissions_mhz` (each MHz strictly positive).

`policy.current_day` is the evaluation day. `policy.min_separation_mhz`, `policy.min_carrier_mhz`, and `policy.im_anchor_mhz` are positive integers. `policy.tier_headroom_drop_mhz` maps each tier string to a non-negative integer drop.

`pool_state.tier_emit_cap` maps each tier to a non-negative integer cap on admitted registry carriers for that tier across all bands combined. `pool_state.band_process_order` is a permutation of the band tags present in the dataset.

`anchors/window.json` supplies integers `reference_mhz` and `guard_close_mhz` (non-negative). Only `reference_mhz` is copied into emitted `intermod_hits.json.anchor_mhz`. The `guard_close_mhz` field is reserved metadata in this dataset revision and does not change any computed field under the `imhr-1` schema version named in the ancillary thresholds file.

## Incident replay

Let `events` be `incident_log.events` filtered to `day <= policy.current_day`. Sort `events` by ascending `day`, then ascending `event_id`. Only events with `accepted == true` apply.

Maintain booleans `compromised[site_id]` (sticky once true) and `frozen[site_id]`. Initialise both false for every site observed in any site file.

For each event in sort order:

- `site_compromise` with string `target_site`: set `compromised[target_site] = true`.
- `site_freeze` with `target_site`: set `frozen[target_site] = true`.
- `site_lift` with `target_site`: set `frozen[target_site] = false`.
- `per_band_noise_lift` with string `target_band` and integer `lift_mhz`: add `lift_mhz` to running `band_min_carrier_add[target_band]` starting from zero for all bands.

Rejected events (`accepted` not true) are ignored entirely.

The evaluation-time frozen flag is `frozen[site_id]` after replay. The compromised flag is `compromised[site_id]` after replay.

## Effective per-band minimum carrier

For each band tag `B`, `effective_min_carrier[B] = policy.min_carrier_mhz + band_min_carrier_add[B]` (missing bands use zero add).

## Adjusted emissions per site

If `compromised[site_id]` is true, the adjusted list is empty.

Otherwise, for each raw frequency `f` in `emissions_mhz` sorted descending, compute `adj = f - policy.tier_headroom_drop_mhz[tier]`. Drop `adj` if `adj < effective_min_carrier[band_tag]`. The remaining integers are `adjusted_mhz` in descending order (sort after drops).

## Registry construction (merge)

The registry is an array of objects `{ "band_tag", "mhz", "site_id", "tier" }` built in admission order; this order is the stable ordering for later outputs.

Initialise tier counters `used_tier[tier] = 0` for all tiers appearing anywhere.

Processing uses **band-major sweeps**. Let `bands = pool_state.band_process_order`. Repeat until a full multi-band round admits no new carrier:

For each `B` in `bands` in array order, iterate `site_id` ascending over every site that is not compromised. Skip a site entirely during the whole audit if `frozen[site_id]` is true after replay (it contributes no carriers). For that `(B, site)` pair, consider only sites whose `band_tag == B`. Walk `adjusted_mhz` descending; the first frequency for that site and band in this round that satisfies all of:

- `used_tier[tier] < pool_state.tier_emit_cap[tier]`
- for every registry entry `r` with `r.band_tag == B`, `abs(mhz - r.mhz) >= policy.min_separation_mhz`

admits one carrier: append `{ "band_tag": B, "mhz": mhz, "site_id", "tier" }`, increment `used_tier[tier]`, and stop scanning further frequencies for this site during this band's sweep for this round (at most one admission per site per band per round).

If a full round across all bands admits nothing, stop.

## Intermodulation hits

Consider unordered pairs of distinct registry entries with the same `band_tag` and different `site_id`. Order the two corners by `(site_id, mhz)` lexicographically (`site_id` ASCII ascending, then `mhz` ascending); let `a` be the MHz at the smaller corner and `b` the MHz at the larger corner. Compute only `t1 = 2*a - b` and `t2 = a + b - policy.im_anchor_mhz` (do not add other IM combinations).

Collect integer `hit_mhz` values among `{t1, t2}` that equal the `mhz` field of any registry entry whose `band_tag` equals the pair's shared band. Deduplicate hit MHz values per pair, sort ascending. If non-empty, emit a hit record.

Hit ordering: sort hit records by `(band_tag asc, site_low asc, mhz_low asc, site_high asc, mhz_high asc)` where `(site_low, mhz_low)` is the lexicographically smaller corner of the pair and the high corner is the other registry entry.

## Outputs

Let `AUDIT_ROOT` be the absolute path in environment variable `IMHA_AUDIT_DIR` when that variable is set to a non-empty string, otherwise `/app/audit`.

Write `registry.json`, `intermod_hits.json`, and `summary.json` under `AUDIT_ROOT` (three separate files).

### `registry.json`

Object keys: `admission_order`, `registry`, `tiers_used`.

- `registry` is the array of admitted objects in admission order (not re-sorted).
- `admission_order` is the list of strings `fmt.Sprintf("%s:%d", site_id, mhz)` for each admission in order.
- `tiers_used` is an object mapping each tier string to its final `used_tier` count after sweeps.

### `intermod_hits.json`

Keys: `anchor_mhz`, `hits`, `im_anchor_mhz`.

- `anchor_mhz` equals `anchors/window.json.reference_mhz`.
- `im_anchor_mhz` equals `policy.im_anchor_mhz`.
- `hits` is an array of objects `{ "band_tag", "hit_mhz", "mhz_high", "mhz_low", "site_high", "site_low" }` where `site_low`/`mhz_low` describe one registry corner and `site_high`/`mhz_high` the other, using the same corner convention as hit ordering. `hit_mhz` is the sorted list from the previous section placed as array `hit_mhz` (ascending).

### `summary.json`

Keys: `adjusted_sites`, `bands`, `current_day`, `frozen_skipped_sites`, `hits`, `incidents_applied`, `registry_carriers`, `sweep_rounds`.

- `current_day` copies `policy.current_day`.
- `registry_carriers` is `len(registry)`.
- `hits` is `len(hits)`.
- `bands` copies `pool_state.band_process_order`.
- `incidents_applied` is the length of the filtered sorted events list.
- `sweep_rounds` counts how many outer repeat rounds executed (including the terminating round that admitted zero).
- `frozen_skipped_sites` lists every `site_id` that was frozen after replay, sorted ascending, deduplicated.
- `adjusted_sites` lists every non-compromised site id with its `adjusted_mhz` array (possibly empty), sorted by `site_id` ascending; each element is `{ "adjusted_mhz", "site_id" }`.

## Canonical minification helper (tests only reference file bytes for fixtures)

When cross-checking nested field hashes in tests, minify with `json.dumps(value, sort_keys=True, separators=(",", ":"))` semantics equivalent to the UTF-8 digest of the canonical merged structure.
