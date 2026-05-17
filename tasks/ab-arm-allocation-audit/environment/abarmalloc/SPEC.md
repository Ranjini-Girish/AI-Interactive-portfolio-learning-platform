# A/B arm allocation audit

Inputs live beside this file. Read `policy.json`, `pool_state.json`, `incidents.json`, every `*.json` under `tiers/`, every `*.json` under `overlays/`, every `*.json` under `experiments/`, and every non-empty line in `anchors/*.txt`. Paths under `ledger/` are packaging noise only.

## Canonical JSON

Emit every artifact as JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Policy

- `grace_days` (non-negative integer): staleness threshold against `last_observation_day`.
- `metric_floor` (integer): only observations with `value` greater than or equal to this floor count toward eligibility.

## Pool state

- `current_day`, `window_start_day`, `window_end_day` (integers): inclusive observation window on the day axis.

Only observations with `window_start_day <= day <= window_end_day` participate.

## Tier registry

Each `tiers/*.json` file defines one tier:

- `tier_id` (string, must match the file basename without `.json`)
- `exposure_cap` (positive integer): maximum summed `eligible_total` across experiments in that tier after the tier-cap pass below

## Overlay merge

Walk `overlays/*.json` in ascending ASCII basename order. Later files overwrite earlier values for the same key:

- `min_observations` (integer, default 1)
- `arm_cap` (integer, default unlimited): maximum experiments listed per tier rollup row
- `exclude_arms` (array of arm_id strings): union every listed id

## Incidents and anchors

Parse `incidents.json` `events` with `kind`, `experiment_id`, `day`, and `accepted`. Collect `anchors/*.txt` lines as two whitespace-separated tokens: `experiment_id` then `forced_status`. Sort the combined anchor list by ascending `experiment_id`; when the same id appears more than once, the later line wins. Apply anchors only for ids present in the experiment set.

Accepted `experiment_compromise` events quarantine the matching experiment regardless of anchors. Accepted `freeze_rollout` events set status `frozen` when not quarantined. Anchor `forced_status` value `pause` sets status `hold` when not quarantined or frozen.

## Experiment records

Each `experiments/*.json` basename without `.json` must equal `experiment_id`. Fields:

- `experiment_id`, `tier` (must match a tier registry entry)
- `parent_id` (optional string; when non-empty must name another experiment whose `experiment_id` is strictly smaller in ASCII order)
- `holdout_pct` (integer 0–100)
- `last_observation_day` (integer)
- `arms`: array of objects with `arm_id` and `observations` (`day`, `value` pairs)

Process experiments in ascending `experiment_id` order. `effective_holdout` starts at `holdout_pct`. When `parent_id` is non-empty and names a loaded parent already processed, set `effective_holdout` to the maximum of the current value and the parent's `effective_holdout`.

## Arm eligibility

For each arm, count participating observations and sum their values. `arm_status` is:

- `excluded` when `arm_id` is listed in merged `exclude_arms`
- `underpowered` when not excluded and the count is strictly less than `min_observations`
- `eligible` otherwise

`stale_flag` is true when `current_day - last_observation_day > grace_days`.

Experiment `status` precedence:

1. `quarantined` when compromised
2. else `frozen` when an accepted `freeze_rollout` targets it
3. else `hold` when anchor forces `pause`
4. else `underpowered` when no arm is `eligible`
5. else `stale` when `stale_flag` is true
6. else `ok`

## Allocation

When status is `quarantined`, `frozen`, or `underpowered`, every arm has `allocation_pct` JSON `null` and `eligible_total` is JSON `null`.

Otherwise let `eligible` be arms with `arm_status` eligible sorted by ascending `arm_id`. Let `budget = 100 - effective_holdout`. Split `budget` across `eligible` with integer division: each arm receives `floor(budget / len(eligible))`, and the remainder is added to the lexicographically smallest `arm_id` in `eligible`. Excluded and underpowered arms receive `allocation_pct` 0. `eligible_total` is the sum of numeric `allocation_pct` values on eligible arms.

## Tier-cap pass

After initial allocations, walk experiments in ascending `experiment_id` within each `tier`. Maintain a running sum of each experiment's `eligible_total` (skip experiments whose `eligible_total` is null). When adding an experiment would make the tier sum exceed that tier's `exposure_cap`, set every arm's `allocation_pct` on that experiment to 0 and set `eligible_total` to 0. Earlier experiments in the tier keep their allocations.

## Tier rollups

For each tier, collect experiments with status in `ok`, `hold`, or `stale` and with `eligible_total` greater than zero after the tier-cap pass. Sort by ascending `experiment_id`, keep the first `arm_cap` entries, and emit objects with `experiment_id` and `eligible_total`. Sort the top-level `tiers` array by ascending `tier_id`.

## Reports

`arm_eligibility.json` lists every eligible arm as `{experiment_id, arm_id}` sorted by `experiment_id` then `arm_id`.

`compromise_report.json` carries `experiment_ids` (distinct compromised ids sorted) and `experiments` (quarantined rows sorted by `experiment_id` with `experiment_id` and `tier`).

## Summary

`summary.json` keys: `current_day`, `experiment_total`, `frozen_total`, `hold_total`, `quarantined_total`, `stale_total`, `underpowered_total`, `window_end_day`, `window_start_day`. Count profiles matching each status label.

## Outputs

Write five files to the audit directory:

1. `experiment_profiles.json` with keys `experiments` then `window_end_day` and `window_start_day` copied from pool state.
2. `tier_rollups.json` with key `tiers`.
3. `arm_eligibility.json` with key `arms`.
4. `compromise_report.json` with keys `experiment_ids` then `experiments`.
5. `summary.json` as above.

## Tooling

Read `AAA_DATA_DIR` defaulting to `/app/abarmalloc` and `AAA_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
