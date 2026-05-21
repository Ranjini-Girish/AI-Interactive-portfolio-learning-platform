# Modular payload chain digest

Normative rules for `/app/mod_chain_lab/`. The workspace prompt names paths, the binary, and the deliverable; every numeric mix, incident gate, scaling rule, sort order, and JSON layout rule lives here.

## Read scope

All paths below are rooted at `/app/mod_chain_lab/`. Only regular files referenced by `catalog.json` are read as frame payloads. Any other file under this directory must not influence the digest.

## Inputs

- `policy.json` fields: `modulus` (integer M > 0), `base` (integer B ≥ 0), `init` (integer H0), `tier_bias` (object mapping tier name to integer bias), `current_day` (integer D).
- `catalog.json` field `streams`: array in file order. Each element has `stream_id` (string) and `frame_paths` (array of relative paths). Read each listed path once in array order and parse one JSON object per file.
- `incidents.json` field `events`: array of incident objects processed in file order; semantics below.
- `pool_state.json` field `terminal_sum_cap`: either JSON `null` or an integer cap C ≥ 0.

## Frame object fields

Each frame JSON object must contain string fields `frame_id`, `tier`, `payload_hex`, and integer field `seq`. Missing fields are treated as empty string for strings and 0 for `seq` when referenced by the formulas (still a valid object for sorting).

## Hex parsing

`payload_hex` must be an even-length string where every character is an ASCII lowercase hex digit (`0-9a-f`). Otherwise the frame is **hex-invalid**: the byte list is empty and the diagnostic token `bad_hex` is recorded for that frame.

## Tier bias

Let T be the `tier` string. If T is a key in `policy.tier_bias`, its bias is the JSON integer at that key. Otherwise the bias is 0 and the diagnostic token `unknown_tier` is recorded for that frame.

## Per-frame elementary digest

Let S be the sum of all decoded byte values (0 if no bytes). Let L be the byte length (0 if no bytes). Let Q be `seq` taken as a signed JSON integer, then reduced modulo M as `((Q % M) + M) % M`. Let TB be the tier bias. The elementary digest is `d = (S + L + Q + TB) % M` using nonnegative representatives in `[0, M-1]`.

## Incidents

Let D be `policy.current_day`. An event with integer fields `start_day` and `end_day` is **active** when `start_day ≤ D` and `D ≤ end_day`.

- `suppress_frame`: fields `frame_id`, `start_day`, `end_day`. When active, frames whose `frame_id` equals this value are removed before sorting and mixing.
- `bias_window`: fields `stream_id`, `addend` (integer), `start_day`, `end_day`. When active for a stream whose id matches, every elementary digest computed for that stream has `d ← (d + addend) % M` after the elementary formula and before the chain step. Multiple active windows on the same stream stack additively before modulo: add the sum of all active `addend` values, then reduce once modulo M.
- `compromise_stream`: fields `stream_id`, `accepted` (boolean), `day` (integer). When `accepted` is true and `D ≥ day`, the entire stream is **quarantined** before any sorting or mixing: emit the quarantine rollup described below and ignore bias windows for that stream.

Incident objects with unknown `kind` are ignored entirely.

## Stream processing order

Process `catalog.streams` in array index order. Each stream is independent.

For a non-quarantined stream:

1. Load frames from `frame_paths` in the order they appear in that stream's array.
2. Drop suppressed frames.
3. Sort the remaining frames ascending by integer `seq`, then ascending by UTF-8 byte order of `frame_id` when `seq` ties.
4. Initialise `H = init mod M`.
5. Walk sorted frames in order. For each frame compute `d`, apply stacked bias offsets for this stream if any bias window is active, then update `H ← ( (H mod M) * (B mod M) + d ) mod M` using 64-bit intermediate arithmetic before each final modulo if needed to avoid overflow in implementation, but the mathematical value is the integer in `[0, M-1]`.

For a quarantined stream:

- Do not run the chain. Emit `terminal_residue = 0`, `mix_steps = 0`, `frames_considered` equal to the number of frames that survive suppression only (still load and suppress to count), `status = "quarantined"`, and include the diagnostic token `stream_compromised` exactly once in `diagnostics`.

## Diagnostics aggregation

For each stream rollup, `diagnostics` is the lexicographically sorted list of distinct diagnostic tokens emitted for any frame in that stream after suppression (quarantine token included as above). Tokens are ASCII strings.

## Terminal scaling

Let the **raw terminal** be the `H` value after the walk for non-quarantined streams, or 0 for quarantined streams.

Let Ssum be the sum of raw terminals across streams that are not quarantined. If `terminal_sum_cap` is null or `Ssum ≤ C`, scaling is off: each emitted `terminal_residue` equals the raw terminal, and `summary.cap_applied` is false with `summary.scaled_sum` null.

If `terminal_sum_cap` is the integer C and `Ssum > C`, scaling is on: for every non-quarantined stream with raw terminal R, emitted `terminal_residue` is `floor(R * C / Ssum)` using real division then floor to an integer. Quarantined streams still emit 0. `summary.cap_applied` is true and `summary.scaled_sum` is the sum of emitted `terminal_residue` values across all streams (an integer).

## Output

Write exactly one regular file `/app/audit/mod_digest.json`. UTF-8 without BOM, two-space indent, ASCII-only strings, sorted object keys at every object level, trailing newline only at EOF.

Top-level keys exactly: `meta`, `stream_rollups`, `summary`.

### `meta`

- `policy_sha256`, `catalog_sha256`, `incidents_sha256`, `pool_sha256`: lowercase hex SHA-256 of the raw bytes of the corresponding input file (`policy.json`, `catalog.json`, `incidents.json`, `pool_state.json`).
- `modulus`, `base`, `init`, `current_day`: numeric copies from `policy.json` (`current_day` mirrors `policy.current_day`).

### `stream_rollups`

Array of objects sorted ascending by `stream_id` UTF-8 bytes. Each object keys exactly: `diagnostics` (array of strings), `frames_considered` (integer), `mix_steps` (integer), `status` (`ok` or `quarantined`), `stream_id` (string), `terminal_residue` (integer after scaling rules).

### `summary`

Keys exactly: `cap_applied` (boolean), `quarantined_streams` (integer count of `quarantined` status), `scaled_sum` (integer or JSON null), `streams` (integer stream count), `total_frames_cataloged` (integer count of all cataloged frame paths across streams), `total_frames_after_suppress` (integer sum of per-stream frames after suppression, including quarantined streams).

## Prohibited writes

Never modify anything under `/app/mod_chain_lab/`. Only create `/app/audit/` if needed and write `mod_digest.json`.
