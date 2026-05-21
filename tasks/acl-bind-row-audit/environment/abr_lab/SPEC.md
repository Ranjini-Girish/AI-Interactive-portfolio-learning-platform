# ACL bind row audit (normative)

UTF-8 JSON without BOM. The audit writes `/app/abr_audit/report.json` as pretty-printed JSON with two ASCII spaces per indent level, ASCII-only text, sorted object keys at every depth, comma+space after commas between values, colon+space after each colon, no trailing spaces on lines, and exactly one trailing newline after the closing brace.

## Inputs under `/app/abr_lab/`

- `policy.json` may be an empty object or carry future flags; the reference audit ignores unknown keys.
- `pool_state.json` with integer `current_step`.
- `incident_log.json` with `events` array. Each event has integer `apply_step`, string `event_id`, string `kind`, and optional fields per kind.
- `grants/*.json` files whose basenames match `^[a-z0-9][a-z0-9_-]*\\.json$`, sorted by POSIX relative path. Each file is one object with `subject` (string), `object_id` (string), and unsigned `rights` (integer, treated as 32-bit for masking).
- `anchors/` and `ancillary/` are packaging stubs and must not be read.

## Incident semantics

Sort events by `apply_step` ascending, then `event_id` lexicographically. `events_seen` is the count of events in that sorted list.

For each event in order:

- If `apply_step > pool_state.current_step`, skip mutations but the event still counts in `events_seen`.
- Otherwise the event is **honored**. Unknown `kind` increments `unknown_event_kinds` and performs no mutation.
- `noop` does nothing.
- `revoke_bits` requires `object_id` (string) and `mask` (integer). For every grant row whose `object_id` matches, replace `rights` with `rights & (~(mask & 0xffffffff))` using two's complement 32-bit semantics (mask is truncated to 32 bits as well).

Revokes apply to the evolving row set in sorted incident order.

## Aggregation

After processing incidents, group rows by `object_id`. For each object:

- `combined_rights` is the bitwise OR of all `rights` values in that group after revokes.
- `subjects` is the sorted list of distinct `subject` strings for that group.

## Output `/app/abr_audit/report.json`

Top-level keys `objects` then `summary`.

`objects` is sorted by `id` ascending. Each element has keys `combined_rights`, `id`, `subjects` (alphabetical order within the object). `subjects` is sorted ascending.

`summary` keys alphabetical:

- `events_seen`
- `objects_considered` (length of `objects`)
- `rows_loaded` (total grant rows read from all grant files)
- `unknown_event_kinds`
