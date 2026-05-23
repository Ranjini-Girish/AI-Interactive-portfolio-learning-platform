# diagnostics.md -- closed code catalogue

`retention_diagnostics.json` contains exactly one entry per event that
emitted at least one diagnostic. The diagnostic codes below form a
*closed set*: emitting any code outside this table is a malformed
output. A single event emits at most one error code (the first
applicable one, as documented in `events.md`); warnings can stack on
the same event when the rules independently fire (e.g. an empty
dataset whose effective rules are all zero).

| code                     | severity | snapshot_id is set? |
|--------------------------|----------|---------------------|
| `E_DUPLICATE_ID`         | error    | yes (the offending would-be id) |
| `E_DUPLICATE_NAME`       | error    | yes (the offending id) |
| `E_SNAPSHOT_NOT_FOUND`   | error    | yes (the missing id) |
| `E_HOLD_PREVENTS_DELETE` | error    | yes (the snapshot id) |
| `E_TICK_NEGATIVE`        | error    | no (`null`) |
| `W_HOLD_ALREADY_PRESENT` | warning  | yes (the snapshot id) |
| `W_HOLD_NOT_PRESENT`     | warning  | yes (the snapshot id) |
| `W_BREAK_HOLDS`          | warning  | yes (the snapshot id) |
| `W_SKIP_HELD`            | warning  | yes (the snapshot id) |
| `W_TICK_ZERO`            | warning  | no (`null`) |
| `W_NO_RULES_DEFINED`     | warning  | no (`null`) |
| `W_DATASET_EMPTY`        | warning  | no (`null`) |

## Sorting

`retention_diagnostics.json.events[]` is sorted by ascending `seq`.
Within a single event, the `diagnostics[]` array is sorted by:

1. `severity_rank` ascending -- `error = 0`, `warning = 1`, `note = 2`.
2. `code` ascending (ASCII).
3. `snapshot_id` ascending (ASCII), with `null` sorting **before** any
   string.

A diagnostic must always include all three fields (`code`, `severity`,
`snapshot_id`). When the event is not bound to a single snapshot,
`snapshot_id` is the JSON `null`.

## Sparseness

Events that emit no diagnostic do not appear in `events[]`. The
top-level shape is `{ "events": [ ... ] }` only -- there is no
`metadata` object, no per-event `kind`, and no per-event `time`.
