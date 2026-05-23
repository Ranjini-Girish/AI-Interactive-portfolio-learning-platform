# Latch echo bin audit (normative)

All JSON uses UTF-8 without a byte order mark. Parse numbers as JSON integers.

## Input layout

The lab root contains `SPEC.md`, `policy.json`, `pool_state.json`, `incident_log.json`, `domain_layout.json`, `anchors/east.json`, `anchors/west.json`, ancillary JSON, and `samples/sample_XX.json` where `XX` is two decimal digits. Ignore other names under `samples/`.

Each sample object has `sample_id` (unique string), `readings` (array of integers >= 0, may be empty), `latch` (integer, may be negative), and `trace_tag` (string, witness only).

`policy.json` fields: `bin_stride` (W >= 2), `skew_mix` (K), `blend_mod` (M >= 2), `pair_span` (P >= 1), `latch_mod` (L >= 1), `echo_max` (boolean), `latch_echo` (boolean).

`pool_state.json` uses `ledger_serial` and `quorum_ring`. Anchors provide integer `lane_add` values.

`incident_log.json` has `masks`: each row has `sample_id` and `zero_slots` (distinct integers). Union masks per sample; zero `readings[j]` for in-range indices before arithmetic.

## Per-sample pipeline

Let W = `bin_stride`, E/V = east/west `lane_add`, L ledger, Q quorum.

1. Apply masks.
2. `adj[i] = readings[i] + ((E*i)+V) mod W` using non-negative remainder.
3. `skew = (((L mod M)*K)+latch+(Q mod W)) mod W`.
4. Prefix sums S[0]=0, S[k]=S[k-1]+adj[k-1] for k=1..n.
5. At each k, `folded = floor((S[k]+skew)/W)/P` (truncating division; inputs stay non-negative).
6. Tally `folded` counts. If `latch_echo` and k mod `latch_mod` == 0, add one extra tally at that step's folded bin.
7. If `echo_max` and histogram non-empty, add `((E+V+latch) mod W)` to the tally at the largest bin key only.

Emit histogram rows with tally > 0 sorted by `bin` ascending. Each row has keys `bin` then `tally`.

## Outputs under the audit directory

### `latch_bins.json`

Object with single key `samples` mapping every discovered `sample_id` (from sorted `samples/sample_*.json` paths) to its histogram array (possibly empty).

### `summary.json`

Keys only: `bin_stride`, `blend_mod`, `echo_max`, `latch_echo`, `latch_mod`, `ledger_serial`, `pair_span`, `quorum_ring`, `skew_mix`, `tail_ledger_sha`, `total_assignments`.

`tail_ledger_sha` is lowercase hex SHA-256 of UTF-8 bytes of comma-joined sorted strings `{sample_id}:{S[n]}`.

`total_assignments` sums each sample's reading count after masking.

## Canonical JSON

Two-space indent, sorted keys at every object, colon plus space, comma newline between properties, ASCII only, exactly one trailing newline after the root brace.

## Harness directories

Non-empty trimmed `LEB_DATA_DIR` replaces `/app/leb_lab`. Non-empty trimmed `LEB_AUDIT_DIR` replaces `/app/audit`. Never modify the lab read root.
