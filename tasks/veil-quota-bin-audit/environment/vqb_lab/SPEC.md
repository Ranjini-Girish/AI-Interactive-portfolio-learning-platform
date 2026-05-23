# Veil quota bin audit (normative)

All JSON uses UTF-8 without a byte order mark. Parse numbers as JSON integers.

## Input layout

The lab root contains `SPEC.md`, `policy.json`, `pool_state.json`, `incident_log.json`, `domain_layout.json`, `anchors/east.json`, `anchors/west.json`, ancillary JSON, and `samples/sample_XX.json` where `XX` is two decimal digits. Ignore other names under `samples/`.

Each sample object has `sample_id`, `readings` (integers >= 0), `quota` (integer), and `trace_tag` (witness only).

`policy.json` fields: `bin_stride` (W >= 2), `skew_mix` (K), `blend_mod` (M >= 2), `pair_span` (P >= 1), `veil_cap` (C >= 0), `quota_mod` (Qmod >= 2), `veil_spill` (boolean).

`pool_state.json` uses `ledger_serial` and `quorum_ring`. Anchors provide `lane_add`.

`incident_log.json` masks behave as in the latch task: union `zero_slots` per `sample_id` before arithmetic.

## Per-sample pipeline

Let W = `bin_stride`, E/V = anchor lane adds, L ledger, Q quorum.

1. Apply masks.
2. `adj[i] = readings[i] + ((E*i)+V) mod W`, then replace with `min(adj[i], veil_cap)`.
3. `skew = (((L mod M)*K)+quota+(Q mod Qmod)) mod W`.
4. Prefix sums and folded bins: same truncating rules as the latch audit (`folded = floor((S[k]+skew)/W)/P`).
5. If `veil_spill` and histogram non-empty, subtract `((E+V+quota) mod W)` from the tally at the smallest bin key only; remove that bin if tally becomes zero or negative.

Emit positive tallies sorted by `bin`.

## Outputs

### `veil_bins.json`

Top-level `samples` object listing every sample id from sorted `sample_*.json` files.

### `summary.json`

Keys: `bin_stride`, `blend_mod`, `ledger_serial`, `pair_span`, `quota_mod`, `quorum_ring`, `skew_mix`, `veil_cap`, `veil_spill`, `tail_ledger_sha`, `total_assignments` with the same tail hash and assignment counting rules as the latch audit.

## Canonical JSON

Identical formatting contract: two-space indent, sorted keys, ASCII, single trailing newline.

## Harness directories

Non-empty trimmed `VQB_DATA_DIR` replaces `/app/vqb_lab`. Non-empty trimmed `VQB_AUDIT_DIR` replaces `/app/audit`. Never modify the lab read root.
