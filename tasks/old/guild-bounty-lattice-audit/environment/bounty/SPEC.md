# Guild bounty lattice audit

Inputs live beside this file. Read `policy.json`, `pool_state.json`, `incidents.json`, every `quests/*.json`, every `guilds/*.json`, and every `submissions/*.json`. Paths under `ledger/` and `anchors/` are packaging noise only.

## Canonical JSON

Emit every artifact as JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Policy

- `min_witness` (integer): minimum witness score for a successful attempt.
- `pity_streak_threshold` (positive integer): consecutive failed attempts on the same `chain_tag` required before pity applies to the next success.
- `pity_multiplier_percent` (positive integer): pity points use integer division `base_points * pity_multiplier_percent // 100`.
- `reputation_cap_by_tier` maps `bronze`, `silver`, and `gold` to per-award point caps.
- `max_prereq_depth` (positive integer): maximum prerequisite walk depth when testing acyclicity.

## Pool state

- `current_day` (integer): evaluation day for incidents and prerequisite day comparisons.
- `season_id` (string): copied into `summary.json`.

## Quests and guilds

Each quest file defines `quest_id`, `tier`, `chain_tag`, `base_points`, and `requires` (array of quest ids). Each guild file defines `guild_id`, `cluster_id`, and `tier_ceiling` (`bronze`, `silver`, or `gold`).

## Submissions and deduplication

Each submissions file lists `guild_id` and `attempts` (`quest_id`, `day`, `witness`). For each `(guild_id, quest_id)` keep exactly one attempt: highest `day`; tie on `day` → highest `witness`; tie on `witness` → the attempt appearing last in the file's `attempts` array.

## Prerequisite graph

Build a directed graph from each `requires` edge (prerequisite → dependent). Detect cycles with depth bounded by `max_prereq_depth`. Quests in a cycle are `chain_blocked` for every guild. For acyclic quests, a winning attempt is `blocked_prereq` when any required quest lacks a winning successful completion on a strictly earlier `day` for the same guild.

## Witness, failure, and pity

An attempt with `witness < min_witness` is `failed` (zero points). It extends the per-`(guild_id, chain_tag)` failure streak. A successful attempt awards `base_points`, unless the failure streak before that success (same guild and `chain_tag`, counting only failed winning attempts since the last success) is at least `pity_streak_threshold`, in which case award `base_points * pity_multiplier_percent // 100` instead. Cap every award at `reputation_cap_by_tier[quest.tier]`. Reset the streak after each success.

Record the preliminary status before incidents: `valid`, `failed`, `blocked_prereq`, or `chain_blocked`.

## Incident passes (in order)

Process accepted incidents with `day <= current_day`. Ignore events whose ids do not exist or whose `kind` is unknown. Count ignored rows in `summary.ignored_incident_events`.

1. `quest_sabotage` with `quest_id`: every completion row for that quest becomes `void` and gains reason `quest_sabotage`.
2. Cluster taint: when a guild has any `void` row, every other guild sharing its `cluster_id` has each row that was `valid` become `tainted` with reason `cluster_taint` (rows already `void`, `failed`, `blocked_prereq`, or `chain_blocked` are unchanged).
3. `guild_freeze` with `guild_id`: all rows for that guild become `frozen` with reason `guild_freeze` (overrides `tainted` but not `void`).
4. `payout_review` with `guild_id` and `target_payout` (`paid` or `withheld`): choose the event with the largest `day` per guild (tie → last in the sorted incident list). Apply only when the guild has no `void` or `tainted` row; set `final_payout` to `target_payout` and add `payout_review` to guild reasons. Otherwise the review is skipped.

`preliminary_payout` for a guild is `paid` when the sum of `points_awarded` over rows still `valid` before step 4 is positive, else `withheld`. `final_payout` starts equal to `preliminary_payout` until a review applies.

## Cluster reputation cap

After statuses are final, for each `cluster_id` and tier sum `points_awarded` over rows with status `valid`. When the sum exceeds `reputation_cap_by_tier[tier]`, repeatedly subtract the award from the valid row with the greatest `day` (tie → lexicographically greatest `quest_id`) until within cap. Record `raw_total` and `capped_total` per tier.

## Outputs

Write six files to the audit directory:

1. `completion_audit.json` — `entries` sorted by `(guild_id, quest_id)`. Each entry includes `guild_id`, `quest_id`, `day`, `witness`, `points_awarded`, `status`, and sorted `reasons`.
2. `quest_graph.json` — `cycles` (array of cycles, each cycle sorted ascending, outer sorted by first id) and `order` (topological list of acyclic quest ids, parents before children, ties by ascending `quest_id`).
3. `guild_ledger.json` — `guilds` sorted by `guild_id`. Each guild has `points_by_tier` (bronze/silver/gold sums counting only `valid` rows after cap trims), `preliminary_payout`, `final_payout`, and sorted `reasons`.
4. `cluster_pool.json` — `clusters` sorted by `cluster_id`. Each cluster has `tiers` mapping tier name to `{raw_total, capped_total}`.
5. `incident_trace.json` — `applied` sorted by `(day, kind, guild_id, quest_id)` with `effect` strings.
6. `summary.json` — `current_day`, `season_id`, `guilds_total`, `quests_total`, `ignored_incident_events`, `by_status` (counts every status enum), `by_preliminary_payout`, `by_final_payout`.

## Tooling

Read `GBL_DATA_DIR` defaulting to `/app/bounty` and `GBL_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
