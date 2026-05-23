# Slew pace floor audit (normative)

All JSON uses UTF-8 without a byte order mark. Parse numbers as JSON integers.

## Input layout

The lab root contains `SPEC.md`, `policy.json`, `pool_state.json`, `incident_log.json`, `domain_layout.json`, `anchors/north.json`, `anchors/south.json`, ancillary JSON, and `samples/sample_XX.json` where `XX` is two decimal digits. Ignore other names under `samples/`.

Each sample object has `sample_id` (unique string), `values` (array of integers >= 0, may be empty), `epoch_tag` (integer, may be negative), and `key_hint` (string, witness only).

`policy.json` fields: `floor_window` (W >= 2), `slew_stride` (S >= 2), `fold_div` (D >= 1), `pace_mod` (P >= 1), `mix_coeff` (K), `blend_mod` (M >= 2), `cap_spill` (boolean), `pace_echo` (boolean).

`pool_state.json` uses `ledger_epoch` and `ring_slot`. Anchors provide integer `lane_add` values.

`incident_log.json` has `masks`: each row has `sample_id` and `zero_slots` (distinct integers). Union masks per sample; zero `values[j]` for in-range indices before arithmetic.

## Per-sample pipeline

Let W = `floor_window`, S = `slew_stride`, N/S = north/south `lane_add`, L = `ledger_epoch`, R = `ring_slot`.

1. Apply masks.
2. `adj[i] = values[i] + ((N*i)+S) mod S` using non-negative remainder (south lane add is the constant term in the spec formula: use north for index term and south for constant offset as in anchors).
3. `skew = (((L mod M)*K)+epoch_tag+(R mod S)) mod S`.
4. Maintain a sliding window of the last W adjusted values. At each step k, let m_k be the minimum value in the current window.
5. Track `running_max` as the maximum m_k seen so far at or before k (undefined until first step).
6. `folded = floor((m_k+skew)/S)/D` (truncating division).
7. Tally `folded` counts. If `pace_echo` and k mod `pace_mod` == 0, add one extra tally at that step's folded bin.
8. If `pace_echo` and m_k equals `running_max` at step k, add one extra tally at that step's folded bin (in addition to step 7 when both apply).
9. If `cap_spill` and histogram non-empty, add `((L+epoch_tag) mod S)` to the tally at the largest bin key only.

Emit histogram rows with tally > 0 sorted by `bin` ascending. Each row has keys `bin` then `tally`.

## Outputs under the audit directory

### `floor_bins.json`

Object with single key `samples` mapping every discovered `sample_id` to its histogram array (possibly empty).

### `summary.json`

Keys only: `blend_mod`, `cap_spill`, `floor_window`, `fold_div`, `ledger_epoch`, `mix_coeff`, `pace_echo`, `pace_mod`, `ring_slot`, `slew_stride`, `tail_floor_sha`, `total_values`.

`tail_floor_sha` is lowercase hex SHA-256 of UTF-8 bytes of comma-joined sorted strings `{sample_id}:{running_max_at_end}` where `running_max_at_end` is the final `running_max` after processing the sample (0 if the sample had no values).

## Canonical JSON

Two-space indent, sorted keys at every object, colon plus space, comma newline between properties, ASCII only, exactly one trailing newline after the root brace.

## Harness directories

Non-empty trimmed `SPA_DATA_DIR` replaces `/app/pace_lab`. Non-empty trimmed `SPA_AUDIT_DIR` replaces `/app/audit`. Never modify the lab read root.
