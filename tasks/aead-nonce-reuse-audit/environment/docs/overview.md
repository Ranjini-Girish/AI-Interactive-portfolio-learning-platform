# AEAD Nonce-Reuse Audit Overview

This task is a deterministic replay of an **AEAD key & nonce audit**.
AEAD constructions (AES-GCM, ChaCha20-Poly1305, ...) require that the
pair `(key, nonce)` is **never** reused for two different encryptions
under the same key. Nonce reuse is catastrophic: a single repeat leaks
the keystream and allows authentication-tag forgery. This auditor
replays an encrypt/install/retire/compromise event log and produces a
forensic report flagging reuse, exhaustion, lifecycle violations,
and idle keys.

The replay reads three JSON inputs from `/app/data/`, processes the
event log in strict ascending `seq` order, and writes five canonical
JSON reports under `/app/output/`.

## Inputs (`/app/data/`)

- `keys.json` -- the seed keyset present *before* `seq 1` fires. Each
  entry carries `key_id` (a string), `algorithm` (one of the allowed
  algorithms in `policy.json`), and `max_uses` (integer, > 0).
  Seed keys start in state `ACTIVE` with `uses_count = 0`,
  `installed_seq = 0`, `last_use_tick = 0`.
- `events.json` -- the ordered event log. Every event has `seq`, `tick`,
  `kind`. Per-kind required fields are documented in `events.md`.
- `policy.json` -- carries `allowed_algorithms` (closed set),
  `idle_retire_ticks`, `near_exhaustion_ratio` (a 2-tuple `[num, den]`
  expressing the threshold as a fraction), and `severity_ranks`.

## Replay model

Events are processed in strict ascending `seq` order. `events.json`
MAY be presented unsorted; the auditor sorts by `seq` ascending before
replay. For each event:

1. Advance `now = event.tick`.
2. Run the **idle-retire sweep**: every `ACTIVE` key whose
   `now - last_use_tick >= policy.idle_retire_ticks` auto-retires
   to `RETIRED`, emitting `N_KEY_IDLE_RETIRED` at the event's `seq`.
   The sweep runs in `key_id` ASCII ascending order and **before** the
   event itself applies.
3. Apply the event. Each kind has its own pre/post conditions and may
   emit diagnostics from the closed catalogue (`diagnostics.md`).

## Outputs (`/app/output/`)

- `key_states.json` -- per-key final snapshot.
- `encryption_log.json` -- per-encrypt outcome log, ordered by `seq`.
- `audit_log.json` -- per-key chronological state-transition log
  (install, retire, exhaust, compromise, idle_retire).
- `diagnostics.json` -- sorted closed-catalogue diagnostic stream.
- `summary.json` -- totals and by-state counts.

Outputs are canonical JSON (2-space indent, sorted keys, ASCII-only,
trailing newline). See `output_format.md` for shapes.
