# Ribbon winding quorum audit

Normative rules for the read-only audit under `/app/rwq_lab/`. Ancillary JSON under `ancillary/` is not read and must not affect outputs.

## Inputs

- `domain_layout.json` contains `ring_order`, a non-empty array of distinct segment ids in cyclic order.
- `index.json` contains `segment_files`, a non-empty array of relative paths under the lab root. Each path must resolve to a UTF-8 JSON segment file. Every id in `ring_order` must appear exactly once across those files; no extra segments are allowed.
- Each segment file contains `segment_id` (string), `tier` (string), `witness` (integer, may be negative), and `flux` (integer).
- `policy.json` contains `schema_version` (integer), `evaluation_day` (integer), `quorum` (integer, at least zero), `winding_modulus` (integer, at least two), and `anchor_weight` (integer, at least zero).
- `pool_state.json` contains `tier_cap`, an object mapping tier name strings to positive integer caps.
- `incident_log.json` contains `windows`, an array (possibly empty). Each window has `until_day` (integer), `tiers` (non-empty array of strings), and `relax` (integer, at least zero).
- `anchors/lo.json` and `anchors/hi.json` each contain `seg_start` and `seg_end`, both ids from `ring_order`.

## Cyclic anchor coverage

Map each segment id to its index in `ring_order` (zero-based). For an anchor pair `(seg_start, seg_end)`, the covered set is every segment encountered when walking forward along `ring_order` from `seg_start` through `seg_end`, inclusive. If the start index is less than or equal to the end index, walk linearly. If the start index is greater than the end index, walk from start through the last ring position, then continue from index zero through end.

For each segment, `anchor_hits` is the count of anchors whose covered set includes that segment. `effective_witness` is `witness + anchor_weight * anchor_hits`.

## Winding

Let `sum_flux` be the integer sum of every segment’s `flux` on `ring_order`. Let `M` be `winding_modulus`. Define `residue = ((sum_flux % M) + M) % M`. The bundle is `winding_ok` when `residue == 0`. When `winding_ok` is false, every segment verdict is `winding_violation` and tier-cap logic is skipped.

## Incident quorum relaxation

For a segment with tier `T`, consider every incident window where `evaluation_day <= until_day` and `T` appears in `tiers`. Let `best_relax` be the maximum `relax` among those windows (zero if none match). `effective_quorum` is `max(0, quorum - best_relax)`.

## Quorum verdict before tier cap

When `winding_ok` is true, a segment is `quorum_ok` if `effective_witness >= effective_quorum`, otherwise `quorum_starved`.

## Tier capacity trimming

When `winding_ok` is true, process tiers in ascending lexicographic order of tier names present in `tier_cap`. For each tier `t` with cap `C`, consider only segments whose tier equals `t` and whose current verdict is `quorum_ok`. While the sum of their `effective_witness` values is strictly greater than `C`, pick the segment among them with the largest index in `ring_order` (the furthest forward on the ribbon). Change that segment’s verdict to `tier_trimmed` and repeat. Trimming does not change numeric witness fields; only the verdict string changes.

After all trimming passes, rename every remaining `quorum_ok` verdict to `passed`.

## Diagnostics

Build an array of objects `{ "code", "segment_id" }`. Include `WINDING` for every `winding_violation`, `QUORUM` for every `quorum_starved`, and `TRIM` for every `tier_trimmed`. Sort by `segment_id` ascending, then `code` ascending.

## Summary object

Emit counts: `diagnostics_total` (length of diagnostics), `passed_count`, `quorum_starved_count`, `tier_trimmed_count`, `winding_violation_count`, `segments_total` (length of `ring_order`), `winding_ok` (boolean), and `schema_version` copied from policy.

## Segment table

`segment_verdicts.json` contains `schema_version` (from policy), `segments`, and `diagnostics`. `segments` is an array in the same order as `ring_order`. Each row has `segment_id`, `tier`, `effective_witness`, `effective_quorum`, and `verdict`.

## Canonical JSON

All emitted JSON must be UTF-8. Serialize with sorted object keys at every object level, no insignificant whitespace, no trailing spaces inside values, numbers rendered as JSON integers without leading zeros, and exactly one newline (`0x0A`) after the closing brace or bracket of each file.

## Environment overrides

When `RWQ_DATA_DIR` is set to a non-empty string, read inputs from that directory instead of `/app/rwq_lab/`. When `RWQ_AUDIT_DIR` is set to a non-empty string, write outputs there instead of `/app/audit/`. Create the audit directory when missing.
