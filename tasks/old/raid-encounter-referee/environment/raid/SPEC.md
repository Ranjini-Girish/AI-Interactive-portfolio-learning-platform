# Raid Encounter Referee Specification

This task consumes JSON fixtures under `/app/raid/` and writes five JSON artifacts
to `/app/results/`.

## Inputs

- `/app/raid/pool_state.json`
- `/app/raid/teams/tiers.json`
- `/app/raid/policy/rules.json`
- `/app/raid/history/duel_history.json`
- `/app/raid/loot/crates.json`
- `/app/raid/incidents/incident_log.json`
- `/app/raid/players/*.json`

### Player schema

Each player file is a JSON object with:
`player_id`, `team_id`, `role`, `rating`, `attendance_streak`,
`loot_tokens`, `bench_credits`, and `loot_need`.

## Incident acceptance and status

Accepted incidents satisfy all conditions:

1. `accepted == true`
2. `day <= pool_state.current_day`
3. `kind` is in `rules.supported_incident_kinds`

For duplicate incidents with same `(scope, target_id, kind)`, keep one winner:
largest `day`; if tied, ASCII-smallest `event_id`.

Kinds map to status ranks:

- `conduct_warning` -> `probation` (rank 1)
- `no_show` -> `suspended` (rank 2)
- `exploit_use` -> `disqualified` (rank 3)
- `pardon` -> `active` (rank 0, but only if no higher-rank incident exists later)

Team incident kind `raid_lockout` applies rank 2 to all players in that team.

Final player status precedence is max rank after applying personal incidents and
team lockout. Status enum is exactly:
`active`, `probation`, `suspended`, `disqualified`.

## Output files

Write exactly:

- `/app/results/match_cards.json`
- `/app/results/loot_draft.json`
- `/app/results/sanction_board.json`
- `/app/results/bench_plan.json`
- `/app/results/summary.json`

## Match cards

Active and probation players are duel-eligible. Others are excluded.

For each eligible player compute:
`combat_score = rating + attendance_streak * 4 + bench_credits * 3`.

Sort eligible players by:
1. `combat_score` descending
2. `rating` descending
3. `player_id` ascending

Pair adjacent entries into duels. If odd, the last becomes a bye.

For each pair `(a,b)`, if `(a,b)` or `(b,a)` appears in history with
`round >= current_round - rematch_window`, try swapping `b` with next unpaired
player to avoid the rematch. If no swap candidate exists, keep the rematch.

Expected winner is higher `rating`; tie by ASCII-smallest `player_id`.

`match_cards.json` schema:
`{ "matches": [ ... ], "byes": [player_id...] }`

Each match object has:
`match_id`, `red_player`, `blue_player`, `pairing_reason`, `expected_winner`.
`pairing_reason` is `score_pair` or `forced_rematch`.

Matches sorted by `match_id`. Byes sorted ascending.

## Loot draft

Each crate has `crate_id`, `slot`, `rarity`.
Only duel-eligible players are candidates.

Candidate priority:
`loot_tokens * 10 + attendance_streak * 2 + bench_credits + winner_bonus`.
`winner_bonus` is `rules.winner_bonus_points` if player is expected winner in any
scheduled match, else `0`.
Add `rules.need_match_bonus` if player `loot_need == slot`.

Probation players cannot receive crates with rarity `epic`.

For each crate pick highest-priority eligible candidate, tie-break by:
1. `bench_credits` descending
2. `player_id` ascending

`loot_draft.json` schema:
`{ "allocations": [ {crate_id, awarded_to, priority_score, rarity, slot}, ... ] }`
sorted by `crate_id`.

## Bench plan

Include duel-eligible players only.

Player `bench_state`:
- `forced_bench` if player is in `byes`
- `hold` if player receives any crate
- `rotate` otherwise

Output schema:
`{ "players": [ {player_id, bench_state, team_id}, ... ] }`
sorted by `(bench_state, player_id)` where state order is
`forced_bench`, `hold`, `rotate`.

## Sanction board

Schema:
`{ "players": [ {player_id, status, sources}, ... ] }`

`sources` is sorted list of applied incident kinds (`raid_lockout` included when
applicable). Player rows sorted by `player_id`.

## Summary

`summary.json` is:
`{ active_count, probation_count, suspended_count, disqualified_count,
duel_count, bye_count, forced_rematch_count, crates_total, crates_epic,
teams_locked_count }`

All summary values are integers.

## Canonical JSON encoding

All output files must be UTF-8 JSON encoded with:

- two-space indentation
- object keys sorted at every level
- trailing newline at file end
