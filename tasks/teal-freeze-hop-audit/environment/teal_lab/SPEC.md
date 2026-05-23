# Normative specification — `teal_lab` bundle

All paths are relative to the data root (`/app/teal_lab/` in the image, or `TSP_DATA_DIR` when set after trimming ASCII whitespace). Read JSON as UTF-8. Unknown fields in JSON objects are ignored unless this document says otherwise.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `domain_layout.json`, `incident_log.json`, every `items/item_*.json` in ascending ASCII filename order, both files under `anchors/`, and every file under `ancillary/`. Emit UTF-8 JSON into the audit root (`/app/audit/` in the image, or `TSP_AUDIT_DIR` when set after trimming) using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by exactly one trailing newline for every emitted file.

Environment routing: when `TSP_DATA_DIR` is non-empty after trimming, read inputs from that directory instead of `/app/teal_lab/`. When `TSP_AUDIT_DIR` is non-empty after trimming, write outputs there instead of `/app/audit/`. When unset or empty, use `/app/teal_lab/` for reads and `/app/audit/` for writes. Create the audit directory when missing.

## Witness JSON

`pool_state.json` and `domain_layout.json` are witness files for this bundle revision. They must remain byte-identical to the shipped copies at verification time. The verifier hashes their bytes.

## Policy and modulus

`policy.json` must contain integer `modulus` with `modulus >= 2`. All modular arithmetic uses `modulus` as the modulus and returns values in `[0, modulus-1]`.

## Cursor replay

Let `M` be `modulus`. Let `cursor_0` be `int(pool_state["cursor_seed"]) % M`.

Build the list `accepted` by scanning `incident_log.json` field `events` in array order and keeping only objects with `"accepted": true` and a string `kind` in the closed set below.

Maintain an integer `cur`. Initialise `cur = cursor_0`.

Define snapshot array `snap` with length `len(accepted) + 1`:

- `snap[0] = cur` immediately after initialisation (before any accepted event is applied).
- For each index `i` zero-based over `accepted`, apply the `i`th event to `cur` using the rules below, then set `snap[i + 1] = cur`.

Incident kinds (only these participate; any other `kind` is ignored entirely, including for advancing snapshots — ignored events are not present in `accepted`):

- `add`: `v = int(value)` when `value` is present, otherwise `0`. Update `cur = (cur + v) % M`.
- `xor_lane`: `v = int(value)` when `value` is present, otherwise `0`. Update `cur = (cur ^ (v & 0xFF)) % M`.
- `mul_wrap`: `v = int(value)` when `value` is present, otherwise `1`. If `(v % M) == 0`, treat the multiplier as `1` instead of zero. Update `cur = (cur * (v % M)) % M` after the zero-to-one guard.

## Anchor knobs

`anchors/a.json` and `anchors/b.json` may each contain integer `knob`; missing `knob` counts as zero. Define `knob_sum = (int(knob_a) + int(knob_b)) % M` using the anchored values wrapped into `[0, M-1]` with `((x % M) + M) % M` before combining if any intermediate subtraction were introduced; here only addition of two wrapped knobs: `knob_sum = ((knob_a % M) + (knob_b % M)) % M`.

## Item ledger

Each item JSON contains string `id`, integer `freeze_idx`, integer `lever`, and integer `offset`.

Let `N = len(accepted)`. Clamp `idx = min(max(int(freeze_idx), 0), N)` so `snap[idx]` is always defined.

Let `L = ((int(lever) % M) + knob_sum) % M`.

Compute `value = (snap[idx] * L + int(offset)) % M`.

Emit `hop_values.json` as `{"entries": [...]}` where each entry has keys `freeze_idx`, `id`, `lever_used`, `offset`, `snap_idx`, `value` (all present). `snap_idx` equals the clamped `idx`. `lever_used` equals `L`. `freeze_idx` in the entry repeats the clamped `idx` (not the raw input) so downstream tools see the effective freeze.

Sort `entries` ascending by ASCII `id`, then ascending by `value` as tie-breaker.

Emit `summary.json` with integer keys `entries`, `knob_sum`, `modulus`, `snap_count` (same as `len(snap)`), `sum_values` (sum of entry `value` fields as a plain integer with no modulus), and integer `terminal_cursor` equal to the final `cur` after all accepted incidents.

## Canonical serializer

Every output file uses the serializer from the Global I/O contract. No BOM.
