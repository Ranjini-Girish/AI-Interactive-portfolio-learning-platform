# events.md -- event semantics

Events are processed in strict ascending `seq` order. The log must be
dense: `seq` runs `0..N-1` with no gaps and no duplicates. A
non-dense log is a malformed input and the binary must exit non-zero.

The schema for `events.json` lives at
`/app/schemas/events_input.schema.json`. The fields actually
consulted depend on `kind`; unrelated fields are ignored.

## `snapshot_create`

Required fields: `dataset`, `id`, `name`.

Resolution order (only the first applicable check fires; no further
state change happens for this event):

1. If `id` already exists in `state` → emit `E_DUPLICATE_ID` with
   `snapshot_id = id` and stop.
2. Else if `(dataset, name)` is already taken by another snapshot →
   emit `E_DUPLICATE_NAME` with `snapshot_id = id` and stop.
3. Otherwise insert the snapshot with `created_at_sec = now_sec` and
   `holders = []`. Increment `snapshots_created`.

## `snapshot_delete`

Required fields: `id`, `force` (bool).

1. If `id` is not in `state` → emit `E_SNAPSHOT_NOT_FOUND` and stop.
2. Else if the snapshot has at least one holder, resolve the
   *effective action*:
   - if `force` is `true` → effective action is `break_holds`,
   - else → effective action is `policy.held_delete_action`.
   The three possible effective actions are:
   - `reject` → emit `E_HOLD_PREVENTS_DELETE` and stop.
   - `skip` → emit `W_SKIP_HELD` and stop.
   - `break_holds` → emit `W_BREAK_HOLDS`, then continue.
3. Remove the snapshot from `state` (clearing its `(dataset, name)`
   entry). Increment `snapshots_deleted_explicitly`.

## `hold_add`

Required fields: `id`, `holder`.

1. If `id` is not in `state` → emit `E_SNAPSHOT_NOT_FOUND` and stop.
2. Else if `holder` is already in the snapshot's holder list → emit
   `W_HOLD_ALREADY_PRESENT` and stop.
3. Else add `holder` to the snapshot's holder list.

## `hold_release`

Required fields: `id`, `holder`.

1. If `id` is not in `state` → emit `E_SNAPSHOT_NOT_FOUND` and stop.
2. Else if `holder` is not in the snapshot's holder list → emit
   `W_HOLD_NOT_PRESENT` and stop.
3. Else remove `holder` from the snapshot's holder list.

## `tick`

Required field: `delta_sec`.

1. If `delta_sec < 0` → emit `E_TICK_NEGATIVE` (with
   `snapshot_id = null`) and stop. The clock is not modified.
2. Else if `delta_sec == 0` → emit `W_TICK_ZERO` (with
   `snapshot_id = null`) and stop. The clock is not modified.
3. Else add `delta_sec` to `now_sec`.

## `retention_run`

Required field: `dataset`.

This is the only event that prunes snapshots. See `retention.md` for
the full bucket-and-keep algorithm. Side effects:

- Increments `retention_runs_executed`.
- Appends one entry to `prune_log.json` for every `retention_run`,
  including runs where every snapshot was kept and runs where the
  dataset was empty (`kept` and `pruned` will then be empty arrays).
- May emit `W_NO_RULES_DEFINED` (when every effective rule is `0`)
  and/or `W_DATASET_EMPTY` (when no snapshot in `state` belongs to
  `dataset`). Both are warnings with `snapshot_id = null`.
