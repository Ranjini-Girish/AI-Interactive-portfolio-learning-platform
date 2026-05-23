# Key State Machine

## States

| state         | meaning                                                       |
| ------------- | ------------------------------------------------------------- |
| `ACTIVE`      | live; may be used for encryption                              |
| `RETIRED`     | explicitly retired (or idle-retired); MUST NOT be used        |
| `EXHAUSTED`   | hit `max_uses`; MUST NOT be used                              |
| `COMPROMISED` | nonce was reused, or `key_compromise` event; MUST NOT be used |

Per-key state held by the engine:

- `key_id` -- the key identifier (string).
- `algorithm` -- one of `policy.allowed_algorithms`.
- `state` -- one of the four states above.
- `max_uses` -- positive integer; engine refuses to register `0`.
- `uses_count` -- how many successful `encrypt` events used this key.
- `installed_seq` -- the event `seq` at which the key was installed
  (`0` for seed keys present in `keys.json`).
- `retired_seq`, `exhausted_seq`, `compromised_seq` -- bookkeeping;
  exactly the matching field is non-`null` when the key reaches that
  state.
- `last_use_tick` -- `tick` of the most recent successful `encrypt`,
  or `0` if none. Updated on every `encrypt` outcome `accepted`.

## Transitions

| from        | trigger                                                | to            |
| ----------- | ------------------------------------------------------ | ------------- |
| (new)       | seed entry in `keys.json` / `key_install`              | `ACTIVE`      |
| `ACTIVE`    | `key_retire`                                           | `RETIRED`     |
| `ACTIVE`    | idle-retire sweep fires                                | `RETIRED`     |
| `ACTIVE`    | `uses_count` reaches `max_uses` (after a successful encrypt) | `EXHAUSTED` |
| `ACTIVE`    | `key_compromise` OR nonce-reuse detected               | `COMPROMISED` |
| `RETIRED`   | `key_retire` again                                     | `RETIRED` *   |
| `RETIRED`   | `key_compromise`                                       | `COMPROMISED` |
| `EXHAUSTED` | `key_retire`                                           | `EXHAUSTED` ** |
| `EXHAUSTED` | `key_compromise`                                       | `COMPROMISED` |
| `COMPROMISED`| `key_retire` / `key_compromise`                       | `COMPROMISED` ** |

`*` -- emits `W_RETIRE_ALREADY_RETIRED`; no state change.
`**` -- emits `E_RETIRE_NOT_ACTIVE` (for retire) or
`W_COMPROMISE_REDUNDANT` (for compromise on COMPROMISED).

`ACTIVE` is the only state in which an `encrypt` can succeed. Any
attempt on a non-`ACTIVE` key is rejected with the matching error
(see `events.md`).

## Nonce-reuse semantics

The auditor maintains, per key, the set of nonce integers it has
already accepted. When an `encrypt(key_id, nonce)` event arrives and
the key is `ACTIVE`:

1. If `nonce` is already in this key's accepted-nonce set, emit
   `E_NONCE_REUSE` with evidence
   `{"first_seq": <int>, "first_tick": <int>}` (the `seq`/`tick` of the
   first accepted encrypt with that nonce). The encrypt is **rejected**
   (`outcome = "rejected"`, `reason = "NONCE_REUSE"`). Immediately
   transition the key to `COMPROMISED`, set
   `compromised_seq = <this event's seq>`, and emit
   `N_KEY_COMPROMISED` with evidence
   `{"trigger": "nonce_reuse", "nonce": <int>}`.
2. Otherwise accept: add `nonce` to the key's accepted-nonce set,
   bump `uses_count`, update `last_use_tick = tick`. If after the bump
   `uses_count == max_uses`, transition the key to `EXHAUSTED`, set
   `exhausted_seq = <this event's seq>`, and emit `N_KEY_EXHAUSTED`.
   Otherwise, if `uses_count * near_exhaustion_ratio[1]
   >= max_uses * near_exhaustion_ratio[0]` (i.e. `uses_count / max_uses
   >= ratio`), and the warning has not already been emitted for this
   key, emit `W_KEY_NEAR_EXHAUSTION` with evidence
   `{"uses_count": <int>, "max_uses": <int>}` (exactly once per key).

Compromise is permanent: a `COMPROMISED` key is never resurrected.
A `RETIRED` or `EXHAUSTED` key never accepts an encrypt.

## Idle-retire sweep

Run at the start of every event, in `key_id` ASCII ascending order:

- For every `ACTIVE` key, if `now - last_use_tick >=
  policy.idle_retire_ticks`, transition to `RETIRED`, set
  `retired_seq = <seq of triggering event>`, emit
  `N_KEY_IDLE_RETIRED` evidence
  `{"last_use_tick": <int>, "now": <int>}`. The sweep may close
  multiple keys per event; each emits its own notice at the same `seq`.
