# Posterior quorum bandit audit (normative)

This document is the single source of truth for parsing inputs, resolving incidents, simulating pulls, and serializing outputs. All arithmetic on integers is exact; do not use floating point in the reference semantics.

## Corpus layout

Read `pool_state.json`, `policy.json`, and `incident_log.json` from the lab root. Load every `arms/*.json` file and every `rounds/*.json` file. Only those two directories participate in simulation; `anchors/` and `ancillary/` are read-only packaging noise for reviewers and must not affect outputs.

Sort arm files by full path string ascending. Sort round files by full path string ascending. Each arm JSON has string `arm_id`, positive integers `prior_alpha`, `prior_beta`, and positive integer `pull_cost`. Each round JSON has string `round_id`, string `phase_token`, array `candidates` of arm ids (strings), and array `pulls`; every pull object has array `votes` where each vote has string `rater_id` and integer `label` in `{0,1}`.

## Policy fields

`policy.json` contains string `audit_schema_version` (must equal `pqb-1`), string `master_seed_hex` (64 lowercase hex chars), non-negative integers `global_alpha` and `global_beta`, non-negative integers `shrink_num` and positive `shrink_den` with `shrink_num <= shrink_den`, positive integer `quorum_distinct`, non-negative integer `budget_tokens`, object `rater_weights` mapping rater ids to positive integer weights, and array `supported_incident_kinds` listing the incident kinds this build understands.

## Incident model

`incident_log.json` has object root with array `incidents`. An incident is active iff all hold: `accepted` is true, integer `day` exists and `day <= current_day` from `pool_state.json`, string `kind` is listed in `policy.supported_incident_kinds`, and every field required below for that kind is present with correct types.

Supported kinds:

- `prior_bump`: fields `arm_id` string, `alpha_delta` positive integer. Apply before shrink: increase that arm's `prior_alpha` by `alpha_delta`.
- `arm_freeze`: fields `arm_id` string, `thaw_day` integer. While `current_day < thaw_day`, the arm is frozen and cannot be selected.
- `quorum_relief`: fields `round_id` string, `relief` non-negative integer. When processing the pull steps for the round whose `round_id` matches, reduce the distinct-rater requirement by `relief`, clamped to a minimum of `1`.

Ignore inactive incidents for logic but count them in `summary.json` as described below.

## Prior mixing (shrink)

For each arm after prior bumps, compute working priors:

`a = floor((prior_alpha * (shrink_den - shrink_num) + global_alpha * shrink_num) / shrink_den)`

`b = floor((prior_beta * (shrink_den - shrink_num) + global_beta * shrink_num) / shrink_den)`

Use truncating division toward zero. If `shrink_num == 0`, numerators simplify to `prior_alpha * shrink_den` and `prior_beta * shrink_den` before division. Ensure `a` and `b` remain at least `1` after mixing; if either would be `0`, set it to `1`.

Posterior simulation starts from these `(a,b)` pairs.

## Deterministic arm score

For a candidate arm `arm_id`, round id `R`, phase token `P`, and global zero-based step index `S`, define `mix = concat(master_seed_hex, ":", R, ":", P, ":", decimal(S), ":", arm_id)` as UTF-8 bytes. Let `h` be the first eight bytes of SHA-256(`mix`) interpreted as an unsigned 64-bit big-endian integer. Let `sum = a + b` for that arm's current posteriors. Let `mean_scaled = floor((a * 1_000_000) / max(sum,1))`. Let `tie = h % 10_000`. The score is `mean_scaled * 10_000 + tie` (integer). Among eligible candidates pick the maximum score; break ties by smallest `arm_id` in ASCII order.

Eligibility for a step: arm appears in this round's `candidates`, is not frozen, exists in the arm table, and `pull_cost <= remaining_budget`. If no arm is eligible, emit a `selection_log` row with `chosen_arm` null, `void_reason` `no_eligible_arm`, still advance the step index, do not spend budget, and do not append `quorum_trace` for that step.

## Pull execution

When an arm is chosen, first subtract its `pull_cost` from `remaining_budget` (integer, never negative). If subtraction would send the budget negative, treat the arm as ineligible for that step (same as `no_eligible_arm` handling: do not subtract, no trace row).

When an arm is chosen and the cost was subtracted, evaluate quorum on that pull's `votes`:

1. Build the set of distinct `rater_id` values with votes whose `label` is `0` or `1`.
2. Required distinct raters = `max(1, policy.quorum_distinct - relief)` where `relief` is the sum of `relief` values from all active `quorum_relief` incidents targeting this `round_id`.
3. If the distinct count is below the requirement, the pull is void with reason `insufficient_quorum`; do not update posteriors.
4. Otherwise compute weighted sums: for each label value, sum `policy.rater_weights[rater_id]` for votes carrying that label. If any vote references a `rater_id` not present in `rater_weights`, the entire input corpus is malformed.
5. If the two sums are equal, void with reason `tie_vote`, no posterior update.
6. Otherwise the Bernoulli outcome `y` is `1` if the sum for label `1` exceeds that for label `0`, else `0`. Increment the arm's `a` by `y` and `b` by `1-y`.

`quorum_trace` records one object per pull row whose simulation reached arm selection with a non-null `chosen_arm`. Skip trace objects when `chosen_arm` is null. Fields sorted as: `chosen_arm` string, `distinct_raters` integer, `label_one_weight` integer, `label_zero_weight` integer, `outcome` (`null` when void else `0` or `1`), `relief_applied` integer, `required_distinct` integer, `round_id` string, `step_index` integer, `void_reason` (string or null), `weighted_winner` (`"one"`/`"zero"`/`null`).

Each `selection_log` step object carries fields sorted as: `budget_after` integer, `chosen_arm` (string or null), `round_id` string, `scores` object mapping every candidate arm id that appeared in this round's `candidates` to its integer score (include frozen or over-budget arms with scores still computed from current posteriors), `step_index` integer, `void_reason` (string or null).

## Output files

`selection_log.json` is a JSON array of those step objects in emission order. `quorum_trace.json` is a JSON array of trace objects in emission order. `flags.json` is an object with sorted key `flags` whose value is the array defined in the Flags section. `posterior_report.json` is an object with sorted key `arms` whose value is the array defined in the Posterior report section. `summary.json` is a single object as defined in the Summary section.

## Processing order

Initialize `remaining_budget = policy.budget_tokens` and `step_index = 0`. Walk sorted round files. Inside each round, walk `pulls` in array order. For each pull perform selection (possibly void before choice), then quorum evaluation as above. After each pull increment `step_index` by `1` even when voided.

## Posterior report

After simulation, emit `posterior_report.json` with object key `arms`: array sorted by `arm_id` ascending. Each arm object carries, in sorted key order: `alpha` and `beta` final posteriors after all updates, `arm_id` string, `pull_cost` integer, `selections` integer counting pulls where this arm was chosen with a successful cost debit, `start_alpha` and `start_beta` integers after shrink mixing, `successes` integer counting non-void pulls where the Bernoulli outcome was `1`, and `voids` integer counting pulls where this arm was chosen but the pull voided after the cost debit (`insufficient_quorum` or `tie_vote`).

## Flags

Emit `flags.json` with key `flags`, an array of objects with keys `code` string, `detail` string, `round_id` string, `step_index` integer. Push `budget_exhausted` when `remaining_budget` hits zero immediately after subtracting pull cost. Push `quorum_void` whenever `void_reason` is `insufficient_quorum` or `tie_vote`. Sort `flags` by `code` asc, then `round_id`, then `step_index`, then `detail`.

## Summary

Emit `summary.json` with sorted keys: `active_incidents` integer count of active incidents, `arms_total` integer, `audit_schema_version` string copied from policy, `audit_version` string copied from `pool_state.json`, `budget_remaining` final integer budget, `current_day` integer, `flags_total` integer size of the `flags` array, `ignored_incidents` integer count of incidents that are not active, `round_files` integer count of round JSON files read, `supported_incident_kinds` array of strings copied from policy and sorted ASCII ascending, `total_steps` integer equal to the number of processed pull rows, `void_steps` integer counting `selection_log` entries whose `void_reason` is not JSON null (string reasons only; `null` is not counted).

## Canonical JSON

Serialize with two ASCII spaces per indent level, `:` followed by a single ASCII space, sorted object keys recursively, no unicode escapes needed (ASCII-only), single trailing newline.

## Malformed input

Exit non-zero and avoid creating the five output filenames when any of: bad JSON, missing required fields, unknown arm id in any round `candidates` list, duplicate `arm_id` values across arm files, `master_seed_hex` not exactly 64 characters of lowercase `0-9a-f`, a vote references a `rater_id` missing from `rater_weights`, or `audit_schema_version` is not `pqb-1`.
