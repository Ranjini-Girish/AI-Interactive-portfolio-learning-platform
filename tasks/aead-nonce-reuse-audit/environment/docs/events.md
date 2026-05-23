# Event Semantics

Every event has `seq` (strictly unique across the log), `tick`
(monotonic non-decreasing once the log is sorted by `seq`), and
`kind`. Required and optional fields and the side effects of each
kind:

## `key_install`
Required: `key_id` (string), `algorithm` (string), `max_uses`
(positive integer).

- If `key_id` already exists in the engine in any state: emit
  `E_DUPLICATE_KEY` evidence `{"prior_state": "<state>"}`. Ignore the
  event.
- If `algorithm` is not in `policy.allowed_algorithms`: emit
  `E_ALGORITHM_UNKNOWN` evidence `{"algorithm": "<value>"}`. Ignore.
- If `max_uses <= 0`: emit `E_INVALID_EVENT` evidence
  `{"reason": "non_positive_max_uses"}`. Ignore.
- Else register the key in state `ACTIVE`, `uses_count = 0`,
  `installed_seq = seq`, `last_use_tick = tick`,
  `retired_seq = exhausted_seq = compromised_seq = null`. Emit
  `N_KEY_INSTALLED` evidence `{"algorithm": "<algo>",
  "max_uses": <int>}`.

## `encrypt`
Required: `key_id`, `nonce` (non-negative integer).

- If `key_id` is unknown: emit `E_KEY_UNKNOWN`. Log the encrypt as
  rejected `reason = "UNKNOWN_KEY"`. No accepted-nonce update.
- If the key state is `RETIRED`: emit `E_KEY_NOT_ACTIVE` evidence
  `{"key_state": "RETIRED"}`. Log rejected `reason = "RETIRED"`.
- If the key state is `EXHAUSTED`: emit `E_KEY_EXHAUSTED`. Log
  rejected `reason = "EXHAUSTED"`.
- If the key state is `COMPROMISED`: emit `E_KEY_COMPROMISED`. Log
  rejected `reason = "COMPROMISED"`.
- Else (key is `ACTIVE`) apply the nonce-reuse semantics from
  `states.md`: either accept (and possibly transition to `EXHAUSTED`
  / emit `W_KEY_NEAR_EXHAUSTION`) or reject with `E_NONCE_REUSE` and
  transition to `COMPROMISED`.

## `key_retire`
Required: `key_id`.

- If `key_id` is unknown: emit `E_RETIRE_UNKNOWN`. Ignore.
- If the key state is `RETIRED`: emit `W_RETIRE_ALREADY_RETIRED`. No
  state change.
- If the key state is `EXHAUSTED` or `COMPROMISED`: emit
  `E_RETIRE_NOT_ACTIVE` evidence `{"key_state": "<state>"}`. No
  state change.
- Else (key is `ACTIVE`) transition to `RETIRED`, set
  `retired_seq = seq`. Emit `N_KEY_RETIRED` evidence
  `{"trigger": "key_retire"}`.

## `key_compromise`
Required: `key_id`, `reason` (string, free-form label).

- If `key_id` is unknown: emit `E_COMPROMISE_UNKNOWN`. Ignore.
- If the key state is `COMPROMISED`: emit `W_COMPROMISE_REDUNDANT`.
  No state change.
- Else transition the key to `COMPROMISED`, set
  `compromised_seq = seq`. Emit `N_KEY_COMPROMISED` evidence
  `{"trigger": "key_compromise", "reason": "<value>"}`.

## `tick`
No required fields besides `seq`, `tick`, `kind`. Purpose is to
advance `now` so the idle-retire sweep can fire.

## Field validation

If an event is missing a required field for its `kind` (other than the
universal `seq`/`tick`/`kind`), emit `E_INVALID_EVENT` evidence
`{"reason": "missing_field"}` and ignore the event. If `kind` is not
in the allowed set, emit `E_INVALID_EVENT` evidence
`{"reason": "unknown_kind"}` and ignore. Missing universal fields
(`seq`/`tick`/`kind`) or malformed JSON cause the binary to **exit
non-zero**.
