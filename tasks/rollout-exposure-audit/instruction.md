The growth team’s rollout auditor at `/app` is incomplete. Finish it in TypeScript under `/app/src/` (Node 20, no extra npm packages). Load assignments from `/app/data/assignments.json`, exposures from `/app/data/exposures.json`, conversions from `/app/data/conversions.json`, pre-period covariates from `/app/data/covariates.json`, and settings from `/app/config/experiments.json`, `/app/config/calendar.json`, and `/app/config/boundaries.json`. Do not change anything under `/app/data/` or `/app/config/`.

Produce `/app/output/rollout_audit.json` with top-level keys `metadata`, `experiments`, and `mutex_violations`. Use 2-space JSON indentation and a trailing newline. Round non-integer floats to six decimals.

Each experiment entry needs `experiment_id`, `srm` (`chi2`, `df`, `p_value`, `flagged`), `variants`, and `sequential_winners`. Each variant needs `variant_id`, `assigned`, `exposed`, `attributed_conversions`, `converted`, `conversion_rate`, and `cuped_rate`. Sort `experiments` by `experiment_id`, variants by `variant_id`, `mutex_violations` by `group_id` then `user_id`, and `sequential_winners` by `analysis_date`.

`metadata` must include `analysis_period` from config, `experiments_analyzed`, `attribution_rule` set to `last_touch_within_window`, and `mutex_policy` set to `latest_assignment_wins_per_group`.

When mutex groups are configured, each user should contribute to at most one experiment in that group—the one tied to their most recent assignment timestamp across competing experiments. `assigned` counts must reflect that eligibility. `srm.flagged` should be true when the assigned variant mix diverges meaningfully from configured weights (use `srm_alpha` from config).

Conversions count only when an exposure on the user’s assigned variant occurs before the conversion timestamp and within `attribution_window_hours`; when several exposures qualify, attribution follows the latest qualifying exposure. `converted` is the number of attributed rows with `value` equal to 1; `conversion_rate` is the ratio of `converted` to `attributed_conversions` (zero when none). `cuped_rate` per variant should adjust conversion outcomes using the pre-period covariate map so baseline differences do not dominate.

`sequential_winners` lists analysis dates from the calendar where one variant’s `cuped_rate` clearly beats the other under the thresholds in `/app/config/boundaries.json`, considering only conversions on or before the end of that UTC day. Each winner record includes `analysis_date`, `winner_variant`, `loser_variant`, `z_score`, and `threshold`.

`mutex_violations` lists users who appear in more than one experiment within the same mutex group. Run the auditor with `TypeScript on Node 22 /app/src/main.js` (or your entrypoint) after fixing the broken modules under `/app/src/`.
