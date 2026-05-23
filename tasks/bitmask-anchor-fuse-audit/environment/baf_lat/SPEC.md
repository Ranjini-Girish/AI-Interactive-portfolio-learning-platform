# Normative specification — `baf_lat` bundle

All paths are relative to the data root (`/app/baf_lat/` in the image, or `BAF_DATA_DIR` when set). Read JSON as UTF-8. Unknown fields in JSON objects are ignored unless this document says otherwise.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `domain_layout.json`, `incident_log.json`, every `items/item_*.json` in ascending ASCII filename order, both files under `anchors/`, and both files under `ancillary/`. Emit UTF-8 JSON into the audit root (`/app/audit/` in the image, or `BAF_AUDIT_DIR` when set) using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by exactly one trailing newline for every emitted file.

Environment routing: when `BAF_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/baf_lat/`. When `BAF_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. When unset or empty, use `/app/baf_lat/` for reads and `/app/audit/` for writes. Create the audit directory when missing.

## Witness JSON

`pool_state.json` and `domain_layout.json` are witness files for this bundle revision. They must remain byte-identical to the shipped copies at verification time. The verifier hashes their bytes.

## Incident model

`incident_log.json` contains an `events` array processed in array order. Only objects with `"accepted": true` participate. All integer math below uses 32-bit two’s-complement intermediates but every masked quantity is reduced with `& 0xFF` before it feeds another step or an output.

Incident kinds:

- `xor_acc`: let `v` be `int(value)` when `value` is present, otherwise zero. Update `xor_acc = (xor_acc ^ (v & 0xFF)) & 0xFF`.
- `fuse_xor`: same `v` rule. Update `fuse_active = (fuse_active ^ (v & 0xFF)) & 0xFF`.
- `tier_skew`: same `v` rule. Update `tier_live = round4(tier_live * (1.0 + ((v & 0xFF) / 256.0)))` where `round4` means `float(format(x, ".4f"))` in Python terms (IEEE-754 binary64 throughout, then the decimal string with four fractional digits, then parsed back to float).

Initial state before the first accepted incident: `xor_acc = 0`, `fuse_active = int(policy["fuse_mask"]) & 0xFF`, `tier_live = float(policy["tier_factor"])`.

## Anchor bundle

`anchors/a.json` and `anchors/b.json` each contain an integer `or_mask` in `[0,255]`. Missing `or_mask` counts as zero.

Define `anchor_lane = (or_mask_a ^ or_mask_b) & 0xFF` and `anchor_or = (or_mask_a | or_mask_b) & 0xFF`.

## Domain segments

`domain_layout.json` contains an object `segments`. Keys are segment names (strings). Each value is an object that may contain integer `lane_xor` in `[0,255]`; missing `lane_xor` counts as zero. Items reference segments by optional string field `segment`; when absent, use `"core"`. When `segment` names a key missing from `segments`, treat `lane_xor` as zero.

## Item ledger

Each item file contains string `id`, integer `mask` in `[0,255]`, and float `scale`.

For every item in ascending ASCII filename order compute, using the final incident state:

1. `lane_xor = int(segments[segment].get("lane_xor", 0)) & 0xFF` with the defaulting rules above.
2. `lane = (anchor_lane ^ lane_xor) & 0xFF`.
3. `blended = ((int(mask) ^ xor_acc) & lane) & 0xFF`.
4. `eff = (((blended & fuse_active) | int(policy["base_or"])) | anchor_or) & 0xFF`.
5. `popcount` is the population count of set bits in the non-negative integer `eff`.
6. `score = round4(popcount * float(scale) * tier_live)`.

Emit `fuse_ledger.json` as `{"entries": [...]}` where each entry is an object with keys `blended`, `effective_mask`, `id`, `lane`, `score` (all present, `blended`/`effective_mask`/`lane` integers, `score` float after `round4`). Sort `entries` ascending by ASCII `id`, then ascending by `effective_mask` as tie-breaker.

Emit `summary.json` with integer `anchor_lane`, integer `anchor_or`, integer `entries`, integer `fuse_mask` (the final `fuse_active` after incidents), float `tier_live` (final after incidents, `round4`), float `total_score` (`round4` of the sum of entry scores), integer `xor_acc`.

Emit `incident_state.json` with the same five incident-derived integers/floats as `summary.json` requires for `xor_acc`, `fuse_mask`, `tier_live`, `anchor_lane`, and `anchor_or` (duplicate values, not recomputed differently). Keys must exist exactly: `anchor_lane`, `anchor_or`, `fuse_mask`, `tier_live`, `xor_acc`.

## Canonical serializer

Every output file uses the serializer from the Global I/O contract. No BOM.
