# Mulligan chain audit (normative)

All inputs are UTF-8 JSON unless noted. The audit anchor day is `pool_state.current_day` (integer). Never mutate anything under `/app/mulligan_pool/`.

## Layout

- `formats/<format_id>.json` — mulligan style and limits.
- `decks/<deck_id>.json` — tier, `maindeck`, `sideboard` (arrays of card name strings).
- `sessions/<session_id>.json` — `session_id`, `deck_id`, `format_id`, `played_day`, `chain` (array of step objects).
- `incidents.json` — `events` array.
- `policy.json`, `pool_state.json`.

Each chain step object has integer `step` (0-based, must equal its index in `chain`), `action` (`mulligan` or `keep`), and `hand` (array of card name strings). Unknown step keys are ignored. The final kept hand is the `hand` on the last step whose `action` is `keep`. If no step has `action` `keep`, the session has no final kept hand.

## Opening hand size

`opening_hand_size` defaults to 7 when absent from `policy.json`; otherwise use the policy integer (≥ 1).

## Effective mulligan cap (per session)

For a session, start with `effective_max = min(format.max_mulligans, policy.max_mulligans_by_tier[deck.tier])` using the same missing-tier rule as before (missing tier key means that tier does not tighten the format cap). If `policy.json` defines integer `shared_mulligan_pool` (≥ 0), sort every session by ascending ASCII `session_id` and walk that list. For the current session, let `prior` be the sum of `mulligan_count` values already computed for sessions with the same `deck_id` whose `session_id` is strictly less than the current session’s `session_id` in that sorted list. Let `room = shared_mulligan_pool - prior` (if negative, use 0). Replace `effective_max` with `min(effective_max, room)`.

Count `mulligan_count` as the number of chain steps with `action` `mulligan` that appear strictly before the last `keep` step; if there is no `keep`, count all `mulligan` steps.

## Hand size by mulligan style

Let `m` be the number of steps with `action` `mulligan` already present earlier in the same chain (before the step being validated). Expected hand length on a step:

- `london`: always `opening_hand_size`.
- `vancouver`: `max(format.min_keep_hand_size, opening_hand_size - m)`. `min_keep_hand_size` defaults to 4 when absent.
- `partial_paris`: `max(1, opening_hand_size - 2 * m)`.

A step has `size_ok` false when `len(hand)` differs from the expected length. `hand_size_mismatch` applies when any step has `size_ok` false OR when there is no final kept hand.

## Merged deck restrictions

For each `deck_id`, collect every `format_id` that appears on any session in the bundle referencing that deck. For each card name that appears in `restricted_counts` of at least one of those formats, the merged limit is the minimum of the integer limits listed for that card among only those formats that define the card; formats that omit the card do not participate in the minimum. After merging, a deck violates when any merged card’s total copies in `maindeck` plus `sideboard` exceed that merged limit. Violation rows are `{ "card", "found", "limit" }` sorted by ascending `card`.

## Incidents

Read `incidents.json` `events`. Keep events with `accepted == true` and `event.day <= current_day`. Sort kept events by ascending `(day, event_id)` for processing order and ledger emission.

Supported kinds:

- `card_ban`: requires `card` (string). The card is banned for sessions with `played_day >= event.day`.
- `deck_compromise`: requires `deck_id`. Sessions using that deck with `played_day >= event.day` are `quarantined`.
- `format_suspend`: requires `format_id`. Sessions using that format with `played_day >= event.day` are `format_suspended`.

Unknown kinds, non-boolean `accepted`, or missing required fields: ignore the event.

## Chain structural validation

A session chain is structurally invalid when any of the following holds: more than one step has `action` `keep`; any step has an `action` string other than exactly `mulligan` or exactly `keep`; any step’s integer `step` differs from its zero-based index inside `chain`. Collect matching reason literals `multiple_keep`, `invalid_action`, and `step_index_drift` respectively (a chain may accumulate more than one reason).

## Verdict precedence (first match wins)

1. `quarantined` — kept `deck_compromise` applies to the session’s `deck_id` and `played_day`.
2. `format_suspended` — kept `format_suspend` applies to the session’s `format_id` and `played_day`.
3. `deck_restriction` — the referenced deck has any merged restriction violation.
4. `banned_card` — the final kept hand contains a card banned for `played_day`.
5. `chain_invalid` — the chain fails structural validation (even when no `keep` exists).
6. `mulligan_exceeded` — `mulligan_count > effective_max` after applying the shared pool rule when present.
7. `hand_size_mismatch` — any `size_ok` false or missing final kept hand.
8. `legal`.

## Reasons array

Emit `reasons` as a strictly increasing ASCII-sorted unique string array. When `verdict` is `legal`, emit `[]`. Otherwise include every literal that applies from this closed set: `deck_compromise`, `format_suspend`, `deck_restriction`, `banned_card`, `invalid_action`, `multiple_keep`, `step_index_drift`, `mulligan_exceeded`, `hand_size_mismatch`. For `quarantined` verdicts, `deck_compromise` must appear even when other defects exist. For `chain_invalid` verdicts, include every structural reason that matched.

`banned_cards_found` lists banned card names present in the final kept hand, sorted ascending ASCII, unique.

## Outputs (five files under `/app/audit/`)

Canonical JSON: UTF-8, two-space indent, ASCII only, object keys sorted lexicographically at every depth, colon plus single space, exactly one trailing newline at EOF.

### session_verdicts.json

`{ "sessions": [ ... ] }` — one object per input session file, sorted by ascending `session_id`. Fields: `session_id`, `deck_id`, `format_id`, `verdict`, `mulligan_count` (int), `banned_cards_found` (array), `reasons` (array).

### mulligan_traces.json

`{ "traces": [ ... ] }` — sorted by ascending `session_id`. Each trace: `session_id`, `steps` array in chain order. Each step: `step`, `action`, `hand_size` (int, `len(hand)`), `size_ok` (bool).

### deck_restrictions.json

`{ "decks": [ ... ] }` — one row per input deck file, sorted by ascending `deck_id`. Fields: `deck_id`, `violations` (array, possibly empty).

### incident_ledger.json

`{ "applied_events": [ ... ] }` — one object per kept incident in process order, keys sorted inside each object: `day`, `deck_id` (omit unless `deck_compromise`), `event_id`, `format_id` (omit unless `format_suspend`), `card` (omit unless `card_ban`), `kind`. Array sorted by `(day asc, event_id asc)`.

### summary.json

Fields (sorted keys): `applied_incident_events` (int), `chain_invalid_sessions` (int), `deck_restriction_hits` (decks with nonempty `violations`), `format_suspended_sessions` (int), `ignored_incident_events` (int), `legal_sessions` (int), `quarantined_sessions` (int), `sessions_total` (int). `ignored_incident_events` is total events minus kept count.
