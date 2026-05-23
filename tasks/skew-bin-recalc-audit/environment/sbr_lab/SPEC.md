# Skew bin recalc audit (normative)

All JSON consumed and emitted in this task uses UTF-8 without a byte order mark. Parse numbers as JSON integers. Treat absent optional fields exactly as documented.

## Input layout

The lab root is a directory that contains at minimum:

- `SPEC.md` (this file; witness only for integrity checks)
- `policy.json`
- `pool_state.json`
- `incident_log.json`
- `domain_layout.json`
- `anchors/east.json` and `anchors/west.json`
- `samples/sample_XX.json` where `XX` is two decimal digits from `00` upward; ignore any other filenames under `samples/`

Each `samples/sample_XX.json` object contains:

- `sample_id` (string, unique across samples)
- `readings` (array of integers, each greater than or equal to zero; may be empty)
- `phase` (integer; may be negative; used exactly as given)
- `spectrum` (string; ignored for computation but must be present for fixture validity)

`policy.json` fields:

- `bin_stride` (integer W with W greater than or equal to 2)
- `skew_mix` (integer K used in skew)
- `blend_mod` (integer M with M greater than or equal to 2)
- `pair_span` (integer P with P greater than or equal to 1)
- `anchor_cross` (boolean)

`pool_state.json` fields used:

- `ledger_serial` (integer L)
- `quorum_ring` (integer Q)

`anchors/east.json` and `anchors/west.json` each contain:

- `lane_add` (integer; may be negative)

`incident_log.json` contains:

- `masks` (array, possibly empty). Each element has `sample_id` (string) and `zero_slots` (array of distinct integers). Apply every mask whose `sample_id` equals the current sample: before any arithmetic, force `readings[j]` to zero for every index `j` listed in `zero_slots` that is within range of the readings array. When multiple mask rows target the same sample, take the union of all indices.

## Core pipeline (per sample)

Let W equal `bin_stride`. Let E be `lane_add` from `east.json` and V be `lane_add` from `west.json`.

1. Start from the (possibly length zero) readings array after applying incident masks.
2. Build `adj` of the same length: for zero-based index i, `lane = ((E * i) + V) mod W` using the mathematical remainder in the range zero through W minus one (the `%` operator in C or Java on non-negative first operand; if `(E*i)+V` is negative, add multiples of W until the value lies in that range).
3. `adj[i] = readings[i] + lane`.
4. Skew: `skew = (((L mod M) * K) + phase + (Q mod W)) mod W` where L is `ledger_serial`, M is `blend_mod`, K is `skew_mix`, phase is the sample phase, Q is `quorum_ring`.
5. Prefix sums: `S[0] = 0`. For k from 1 through n where n is the length of `adj`, `S[k] = S[k-1] + adj[k-1]`.
6. For each k from 1 through n inclusive, compute `raw = floor((S[k] + skew) / W)` using integer division toward negative infinity only applies if numerator is negative; for this task all values are non-negative, so normal truncating division is equivalent.
7. Folded bin: `folded = floor(raw / P)` where P is `pair_span`.
8. Tally counts in a map from `folded` to occurrence count across all k.
9. If `anchor_cross` is true and the map is non-empty, let `b_min` be the smallest key present in the map. Add `carry = ((E + V + phase) mod W)` (same remainder convention as step 2) to the tally stored at `b_min` only.

Emit histogram rows only where the final tally is strictly greater than zero. Sort rows by `bin` ascending. Each row is an object with keys `bin` then `tally` (two-space indent order in the canonical serializer is governed by sort below).

## Output artifacts

Write under the audit directory (see harness variables below) exactly two files:

### `skew_bins.json`

Top-level object with a single key `samples` whose value is an object mapping each `sample_id` to that sample's histogram array (possibly empty). The `samples` object must list every `sample_id` discovered from the sorted filename order of `samples/sample_XX.json` files (sorted lexicographically by full relative path under the lab root).

### `summary.json`

Object with keys only from this set, sorted lexicographically when serialized:

- `anchor_cross` (boolean copy from policy)
- `bin_stride` (integer)
- `blend_mod` (integer)
- `ledger_serial` (integer)
- `pair_span` (integer)
- `quorum_ring` (integer)
- `skew_mix` (integer)
- `tail_ledger_sha` (string): lowercase hex SHA-256 of the UTF-8 bytes of the string formed by sorting the list of strings `"{sample_id}:{S[n]}"` for every processed sample (one entry per sample) lexicographically and joining with commas with no trailing comma.
- `total_assignments` (integer): sum over samples of each sample's `n` (the count of readings after masking, equal to the number of prefix steps).

## Canonical JSON encoding

Both output files must be written as JSON with:

- UTF-8 encoding
- Two ASCII spaces per indent level
- Colon plus one ASCII space after each key
- Comma plus newline between properties
- `sort_keys=true` at every object level (all keys recursively sorted)
- `separators=(",", ": ")` between tokens as in Python's `json.dumps`
- Exactly one trailing newline after the closing brace

## Harness directories

When environment variable `SBR_DATA_DIR` is set to a non-empty string after trimming ASCII whitespace, it replaces the default lab root `/app/sbr_lab`. When `SBR_AUDIT_DIR` is set to a non-empty trimmed string, it replaces `/app/audit`. Empty or unset variables keep the defaults. Never modify any file under the lab read root.
