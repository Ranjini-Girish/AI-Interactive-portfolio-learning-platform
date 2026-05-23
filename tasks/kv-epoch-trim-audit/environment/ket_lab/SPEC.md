# KV epoch trim audit (normative)

All JSON uses UTF-8 without a byte order mark. Parse numbers as JSON integers.

## Input layout

The lab root contains `SPEC.md`, `policy.json`, `pool_state.json`, `manifest.json`, `epochs.json`, `spill_links.json`, `incident_log.json`, `domain_layout.json`, `anchors/east.json`, `anchors/west.json`, ancillary JSON, `meta/seq.json`, `grid/dims.json`, and `samples/sample_XX.json`.

Each sample has `sample_id`, `epoch`, `values` (integers >= 0), `epoch_tag`, and `key_hint` (witness only).

`policy.json`: `trim_window` (W >= 2), `epoch_stride` (S >= 2), `fold_div` (D >= 1), `halve_mod` (H >= 1), `mix_coeff`, `blend_mod` (M >= 2), `epoch_spill`, `trim_echo`, `link_walk` (boolean).

`manifest.json`: `cal_tag`, `run_tag`. When they differ, `effective_fold_stride = (epoch_stride + 1) / 2` (integer division); when equal, `effective_fold_stride = epoch_stride`. Lane adds use `epoch_stride`.

`epochs.json`: `current_epoch`. Stale when `epoch < current_epoch - 1`.

`spill_links.json`: `edges` with `from`, `to`. Process in ascending `(from, to)` order.

Incident masks zero in-range value slots before arithmetic.

## Per-sample pipeline

Let W = `trim_window`, S = `epoch_stride`, F = `effective_fold_stride`.

1. Apply masks.
2. `adj[i] = values[i] + ((east*i)+west) mod S`.
3. `skew = (((ledger_epoch mod M)*mix_coeff)+epoch_tag+(ring_slot mod F)) mod F`.
4. Sliding window of last W adjusted values. At step k, let M_k be the **minimum** in the window when stale, else the **maximum**.
5. Track `running_extreme`: for stale samples, the maximum M_k seen so far; for non-stale, the minimum M_k seen so far (undefined until first step).
6. `folded = floor((M_k+skew)/F)/D`; tally. If `trim_echo` and k mod `halve_mod` == 0, extra tally. If `trim_echo` and M_k equals `running_extreme` at k, another extra tally (stack with halve-mod when both fire).
7. If `epoch_spill` and not stale and histogram non-empty, add `((ledger_epoch+epoch_tag) mod F)` to the **smallest** bin; record that bin as spill target for the sample.

## Link walk (when `link_walk` is true)

After all samples, for each spill link `(from, to)` in sort order: if `from` recorded spill bin `b`, add one tally at bin `b` in `to`'s histogram.

## Outputs

### `trim_bins.json`
`samples` maps each `sample_id` to sorted histogram rows.

### `spill_events.json`
`events` sorted by `from`, `to`, `bin`; each row has `from`, `to`, `bin`, `delta` (1).

### `summary.json`
Keys: `blend_mod`, `effective_fold_stride`, `epoch_spill`, `epoch_stride`, `fold_div`, `halve_mod`, `ledger_epoch`, `mix_coeff`, `ring_slot`, `spill_propagate_total`, `stale_sample_total`, `tail_trim_sha`, `total_values`, `trim_echo`, `trim_window`.

`tail_trim_sha`: SHA-256 of sorted `{sample_id}:{running_extreme_at_end}` (0 if empty). `spill_propagate_total`: spill event count.

## Canonical JSON

Two-space indent, sorted keys, colon plus space, ASCII, one trailing newline per root.

## Harness

`KET_DATA_DIR` defaults `/app/ket_lab`; `KET_AUDIT_DIR` defaults `/app/audit`. Never modify the lab read root.
