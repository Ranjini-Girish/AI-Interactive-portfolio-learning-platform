Arena Reseed Planner Specification

Inputs live under `/app/league`.
Output files must be written to `/app/plan`.

Clock source:
- Read `current_day` from `pool_state.json`.
- Only incident events with `accepted=true` and `day <= current_day` are active.

Input files:
- `policy.json`
- `pool_state.json`
- `incident_log.json`
- `teams/*.json`
- `arenas/*.json`

Team schema (`teams/*.json`):
- `team_id` (string, unique)
- `tier` (`gold` or `silver`)
- `seed_score` (int)
- `home_region` (string)
- `stamina` (int)
- `roster_size` (int)
- `preferred_arena_ids` (array of arena ids)

Arena schema (`arenas/*.json`):
- `arena_id` (string, unique)
- `region` (string)
- `capacity_band` (`large`, `medium`, `small`)

Policy fields:
- `min_stamina` (int)
- `min_roster_size` (int)
- `max_matches_per_arena` (int)
- `participation_points` (int)
- `rivalry_bonus` (int)
- `suspended_penalty` (int)
- `tier_priority` (map: `gold` and `silver` -> int)
- `rivalry_pairs` (array of 2-element arrays of team ids; order-insensitive)

Incident events (`incident_log.json`):
- `event_id` (string)
- `day` (int)
- `accepted` (bool)
- `kind` (`suspension`, `arena_lock`, `stamina_override`)
- For `suspension`: `team_id`
- For `arena_lock`: `arena_id`
- For `stamina_override`: `team_id`, `new_stamina`

Processing rules:
1. Effective stamina:
   - Start from team `stamina`.
   - Apply the latest active `stamina_override` for each team.
   - "Latest" means largest `day`; if tied, ASCII-smallest `event_id`.
2. Suspensions:
   - Any team with an active `suspension` is suspended.
3. Locked arenas:
   - Any arena with an active `arena_lock` is locked.
4. Eligibility:
   - A team is active if all are true:
     - not suspended
     - effective stamina >= `min_stamina`
     - roster_size >= `min_roster_size`
5. Active-team ordering:
   - Sort by:
     1) descending `tier_priority[tier]`
     2) descending `seed_score`
     3) ascending `team_id`
6. Pairing:
   - Pair adjacent teams from sorted active list.
   - If odd count, final team is benched with reason `odd_team_out`.
7. Rivalry detection:
   - A pair is rivalry if the unordered pair appears in `rivalry_pairs`.
8. Arena candidates:
   - Rivalry pair: all arenas are candidates (locks and cap are ignored for eligibility).
   - Non-rivalry pair: arena must be unlocked and current assigned count < `max_matches_per_arena`.
9. Arena score:
   - `+2` if both teams have `home_region` equal to arena `region`.
   - Else `+1` if either team home region equals arena region.
   - `+1` if arena id is in either team's `preferred_arena_ids`.
   - Capacity bonus: `large=2`, `medium=1`, `small=0`.
   - Choose highest score, tie by ascending `arena_id`.
10. Match status:
   - If no candidate arena exists: status `unassigned`, `arena_id=null`, `arena_locked_bypass=false`.
   - Else status `scheduled`, set arena id.
   - `arena_locked_bypass=true` only when selected arena is locked and pair is rivalry.
11. Arena load:
   - Every scheduled match increments the selected arena count.
   - `overbooked=true` if final `scheduled_count > max_matches_per_arena`.
12. Standings points:
   - Start all teams at 0.
   - Each scheduled match grants both teams `participation_points`.
   - If scheduled rivalry match, both teams also gain `rivalry_bonus`.
   - Suspended teams add `suspended_penalty`.
13. Bench reasons:
   - `suspended`
   - `small_roster`
   - `low_stamina`
   - `odd_team_out`
   - A suspended team is always labeled `suspended`.

Output files (all required):
1. `match_plan.json`
   - Array sorted by ascending `match_id`.
   - Objects: `match_id`, `team_a`, `team_b`, `rivalry`, `status`, `arena_id`, `arena_locked_bypass`.
2. `arena_load.json`
   - Array sorted by ascending `arena_id`.
   - Objects: `arena_id`, `locked`, `scheduled_count`, `overbooked`.
3. `bench_report.json`
   - Array sorted by ascending `team_id`.
   - Objects: `team_id`, `reason`, `effective_stamina`.
4. `standings_projection.json`
   - Array sorted by ascending `team_id`.
   - Objects: `team_id`, `projected_points`, `status` where status is `active` or `benched`.
5. `summary.json`
   - Object keys:
     - `total_teams`
     - `active_teams`
     - `matches_scheduled`
     - `matches_unassigned`
     - `rivalry_matches`
     - `benched_count`
     - `suspended_count`
     - `locked_arenas`
     - `overbooked_arenas`

JSON encoding for every output file:
- UTF-8 text
- `indent=2`
- keys sorted alphabetically
