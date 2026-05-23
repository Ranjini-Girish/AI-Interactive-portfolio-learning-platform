# Event Semantics

Each event has a `seq`, an `op`, and a subset of the optional fields
`sa_id`, `top`, `window_size`, `owner`, and `esp_seq` (filled with `null`
when unused). Unused fields MUST be present and `null` -- the input file
always emits the same key set per event.

## `add_sa`

Required: `sa_id`, `top`, `window_size`, `owner`. Adds a fresh SA. Failure
modes (in priority order):

1. `sa_id` has been observed anywhere earlier in the trace (in `sas.json`,
   in a previous `add_sa`, or via `create_passive`) -> emit
   `E_DUPLICATE_SA` with `sa_id`, no state change. Whether the previous
   holder is still in the live table or was removed by `delete_sa` does
   not matter.
2. `window_size` is not in `policy.window_sizes_allowed` -> emit
   `E_INVALID_WINDOW` with `sa_id`, no state change.
3. `top < 0` -> emit `E_INVALID_INITIAL_TOP` with `sa_id`, no state
   change.
4. Otherwise install the SA. Its bitmap starts all-zero (no historical
   acceptances are reconstructed); only future `recv` events write bits.

## `delete_sa`

Required: `sa_id`. Removes the SA with that id from the live table. If
the id is not in the live table (either never observed, or already
deleted), emit `E_UNKNOWN_SA` with `sa_id` and make no state change. The
removed SA's per-id observation is NOT cleared -- the id is still
considered observed for `E_DUPLICATE_SA` checks. A successful
`delete_sa` is silent (no diagnostic).

## `rekey`

Required: `sa_id`, `window_size`. Resets the named SA's anti-replay state
in place: `top` becomes 0, the bitmap becomes all-zero (sized for the new
window), the per-SA `rekeys` counter increments by 1, and the new
`window_size` replaces the previous one. The per-SA `recv_total`,
`accepted`, `replays`, and `too_old` counters are NOT reset by rekey --
they are lifetime per-SA-id counters and continue to accumulate. Failure
modes (in priority order):

1. `sa_id` missing from the live SA table -> `E_UNKNOWN_SA`.
2. `window_size` not in `policy.window_sizes_allowed` -> `E_INVALID_WINDOW`
   with `sa_id`, no state change.

## `recv`

Required: `sa_id`, `esp_seq`. Required `esp_seq >= 1` (zero is a
malformed input, see below). Drives the anti-replay decision and is the
only event that emits a row in `packet_decisions.json`. Decision rules
(apply the first matching branch):

1. `sa_id` is not present in the live SA table:
   - under `policy.on_unknown_sa == "drop"`: emit `E_UNKNOWN_SA` with
     `sa_id`, decision `unknown_drop`. No SA created. The
     `drop_unknown_sa` summary counter increments.
   - under `policy.on_unknown_sa == "create_passive"`: install a fresh SA
     with `top = 0`, `window_size = policy.window_sizes_allowed[0]`,
     `owner = "passive"`, then continue with branch 2 below using the
     newly created SA. Set `passive_created = true` on the decision row,
     emit `N_PASSIVE_CREATED` as the diagnostic, decision `accept_passive`
     instead of `accept`. The `passive_created_count` summary counter
     increments. The newly observed `sa_id` is recorded so any later
     `add_sa` for the same id fails with `E_DUPLICATE_SA`.
2. `esp_seq > sa.top`: shift the bitmap left by `(esp_seq - sa.top)` bits
   (any bits that move past position `window_size - 1` are discarded),
   set position 0 to 1, set `sa.top = esp_seq`. Decision `accept` (or
   `accept_passive` if branch 1 created the SA). Per-SA `accepted` and
   `recv_total` increment.
3. `esp_seq == sa.top`: position 0 is already 1, so this is a replay of
   the head. Apply the replay action (see below).
4. `0 < sa.top - esp_seq < sa.window_size` (`esp_seq` falls inside the
   window): let `offset = sa.top - esp_seq`. If bit `offset` is 1, replay
   action. If bit 0, accept by setting bit `offset` to 1 (the bitmap is
   otherwise unchanged). Decision `accept`, `accepted` and `recv_total`
   increment.
5. `sa.top - esp_seq >= sa.window_size` (out of window on the low side):
   too-old action.

## Replay action (branches 3 and 4 hit a set bit)

- Per-SA `recv_total` and `replays` increment in every replay branch
  regardless of policy.
- The diagnostic on the row is `W_REPLAY` (`sa_id`).
- Under `policy.on_replay == "drop"`: decision `replay_dropped`. The
  bitmap is unchanged and `accepted` is NOT incremented.
- Under `policy.on_replay == "log_only"`: decision `replay_logged`. The
  bitmap is unchanged but `accepted` IS incremented (the packet is
  treated as having reached the upper layer).

## Too-old action (branch 5)

- Per-SA `recv_total` and `too_old` increment in every too-old branch
  regardless of policy.
- The diagnostic on the row is `W_TOO_OLD` (`sa_id`).
- Under `policy.on_too_old == "drop"`: decision `too_old_dropped`. The
  bitmap is unchanged and `accepted` is NOT incremented.
- Under `policy.on_too_old == "log_only"`: decision `too_old_logged`. The
  bitmap is unchanged but `accepted` IS incremented.

## Malformed input

The simulator exits non-zero (without writing a complete output set) when
any of the following holds:

- any input file is not valid JSON,
- a required field is missing or has the wrong type,
- `events.json`'s `seq` values are not the dense range `0..N-1` in
  ascending order,
- a `recv` carries `esp_seq <= 0`,
- `sas.json` declares two SAs with the same `id`,
- an SA's `window_size` (in `sas.json`) is not in
  `policy.window_sizes_allowed`, or any declared `top` is `< 0`,
- `policy.window_sizes_allowed` is empty, contains a value `<= 0`,
  or any value `> 4096`,
- `policy.min_hot_threshold` is `< 0`.
