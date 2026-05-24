# Veil quota bin audit (normative)

All JSON uses UTF-8 without a byte order mark. Parse numbers as JSON integers.

## Input layout

The lab root contains `SPEC.md`, `policy.json`, `pool_state.json`, `incident_log.json`, `domain_layout.json`, `anchors/east.json`, `anchors/west.json`, ancillary JSON, and `samples/sample_XX.json` where `XX` is two decimal digits. Ignore other names under `samples/`.

Each sample object has `sample_id`, `readings` (integers >= 0), `quota` (integer), and `trace_tag` (witness only).

`policy.json` fields: `bin_stride` (W >= 2), `skew_mix` (K), `blend_mod` (M >= 2), `pair_span` (P >= 1), `veil_cap` (C >= 0), `quota_mod` (Qmod >= 2), `veil_spill` (boolean).

`pool_state.json` uses `ledger_serial` and `quorum_ring`. Anchors provide `lane_add`.

`incident_log.json` has `masks`: each row has `sample_id` and `zero_slots` (distinct integers). Union masks per sample; zero `readings[j]` for in-range indices before arithmetic.

## Per-sample pipeline

Let W = `bin_stride`, E/V = anchor lane adds, L ledger, Q quorum.

1. Apply masks.
2. `adj[i] = readings[i] + ((E*i)+V) mod W`, then replace with `min(adj[i], veil_cap)`.
3. `skew = (((L mod M)*K)+quota+(Q mod Qmod)) mod W`.
4. Prefix sums S[0]=0, S[k]=S[k-1]+adj[k-1] for k=1..n.
5. At each k, `folded = floor((S[k]+skew)/W)/P` (truncating division; inputs stay non-negative).
6. Tally `folded` counts.
7. If `veil_spill` and histogram non-empty, subtract `((E+V+quota) mod W)` from the tally at the smallest bin key only; remove that bin if tally becomes zero or negative.

Emit histogram rows with tally > 0 sorted by `bin` ascending. Each row has keys `bin` then `tally`.

## Outputs

### `veil_bins.json`

Object with single key `samples` mapping every discovered `sample_id` (from sorted `samples/sample_*.json` paths) to its histogram array (possibly empty). Each histogram entry is an object with integer keys `bin` (the folded bin index) and `tally` (the positive count for that bin). Map each sample id directly to the array; do not wrap the array in another object.

### `summary.json`

Keys: `bin_stride`, `blend_mod`, `ledger_serial`, `pair_span`, `quota_mod`, `quorum_ring`, `skew_mix`, `veil_cap`, `veil_spill`, `tail_ledger_sha`, `total_assignments`.

Copy policy and pool integers into the matching keys. `tail_ledger_sha` is lowercase hex SHA-256 of the UTF-8 bytes of comma-joined lexicographically sorted strings `{sample_id}:{S[n]}` for every processed sample (one entry per sample), where `S[n]` is the prefix sum after the final reading index (the running sum after the last prefix step in the per-sample pipeline). `total_assignments` is the sum over processed samples of each sample's reading count after masking.

## Canonical JSON

Identical formatting contract: two-space indent, sorted keys, ASCII, single trailing newline.

## Harness directories

Non-empty trimmed `VQB_DATA_DIR` replaces `/app/vqb_lab`. Non-empty trimmed `VQB_AUDIT_DIR` replaces `/app/audit`. Never modify the lab read root.
