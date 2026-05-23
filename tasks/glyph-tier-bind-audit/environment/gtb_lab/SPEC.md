# Glyph tier bind audit (normative)

All JSON uses UTF-8 without a byte order mark. Parse numbers as JSON integers.

## Input layout

The lab root contains `SPEC.md`, `policy.json`, `pool_state.json`, `manifest.json`, `epochs.json`, `bind_edges.json`, `incident_log.json`, `domain_layout.json`, `anchors/north.json`, `anchors/south.json`, ancillary JSON, `meta/seq.json`, `grid/dims.json`, and `samples/sample_XX.json` where `XX` is two decimal digits.

Each sample has `sample_id`, `epoch`, `glyphs` (integers >= 0), `tier_shift`, and `bind_tag` (witness only).

`policy.json`: `tier_stride` (W >= 2), `mix_coeff`, `blend_mod` (M >= 2), `chain_span` (P >= 1), `cooldown_mod` (C >= 1), `tier_spill`, `cooldown_echo`, `bind_walk` (boolean).

`manifest.json`: `cal_tag` and `run_tag`. When they differ, `effective_fold_stride = (tier_stride + 1) / 2` using integer division; when equal, `effective_fold_stride = tier_stride`. Lane bias always uses `tier_stride`.

`epochs.json`: `current_epoch`. A sample is stale when `epoch < current_epoch - 1`.

`bind_edges.json`: `edges` with `from` and `to` sample ids. Process edges in ascending lexicographic order of the pair `(from, to)`.

`pool_state.json`: `epoch_serial`, `ring_mod`. Incident masks zero in-range glyph slots before arithmetic.

## Per-sample pipeline

Let W = `tier_stride`, F = `effective_fold_stride`, N/S = north/south `lane_bias`.

1. Apply masks.
2. `adj[i] = glyphs[i] + ((N*i)+S) mod W`.
3. `skew = (((epoch_serial mod M)*mix_coeff)+tier_shift+(ring_mod mod F)) mod F`.
4. `span = chain_span * 2` when stale, else `chain_span`.
5. Prefix XOR: X[0]=0, X[k]=X[k-1] XOR adj[k-1].
6. At each k, `folded = floor((X[k]+skew)/F)/span`; tally. If `cooldown_echo` and k mod `cooldown_mod` == 0, add one extra tally at that bin.
7. If `tier_spill` and not stale and histogram non-empty, add `((N+S+tier_shift) mod F)` to the largest bin only; record that bin as the sample spill target.

## Bind walk (when `bind_walk` is true)

After all samples, for each bind edge `(from, to)` in sort order: if `to` recorded a spill target bin `b`, add one tally at bin `b` in `from`'s histogram (create the row if needed).

## Outputs

### `tier_bins.json`
`samples` maps every discovered `sample_id` to histogram rows (`bin`, `tally`), bins ascending, omit tally <= 0.

### `bind_events.json`
`events` lists each bind walk increment sorted by `from`, then `to`, then `bin`. Each row: `from`, `to`, `bin`, `delta` (always 1).

### `summary.json`
Keys: `bind_propagate_total`, `blend_mod`, `chain_span`, `cooldown_echo`, `cooldown_mod`, `effective_fold_stride`, `epoch_serial`, `mix_coeff`, `ring_mod`, `stale_sample_total`, `tier_spill`, `tier_stride`, `tail_epoch_sha`, `total_glyphs`.

`tail_epoch_sha`: SHA-256 hex of comma-joined sorted `{sample_id}:{X[n]}`. `total_glyphs`: glyph counts after masking. `bind_propagate_total`: count of bind events emitted.

## Canonical JSON

Two-space indent, sorted keys at every object, colon plus space, comma newline, ASCII only, one trailing newline per root.

## Harness

`GTB_DATA_DIR` defaults `/app/gtb_lab`; `GTB_AUDIT_DIR` defaults `/app/audit`. Never modify the lab read root.
