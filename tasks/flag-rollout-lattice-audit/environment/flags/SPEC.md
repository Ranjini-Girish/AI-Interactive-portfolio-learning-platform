# Feature Flag Rollout Audit Specification

All inputs live under `/app/flags`. The current day is `pool_state.current_day`. The audit writes five JSON files under `/app/audit`: `rollout_matrix.json`, `exposure_budget.json`, `dependency_waves.json`, `incident_journal.json`, and `summary.json`.

Canonical JSON means UTF-8, sorted object keys, two-space indentation, and a trailing newline. Arrays use the sort order named below.

Segments form a rooted tree by `segment_id` and `parent_id`. A segment override applies to its named segment and every descendant. For a flag-segment pair, choose the matching override with highest `priority`; ties keep the earlier override entry. If no override matches, use `default_pct`. Sort rollout rows by `(flag_id, segment_id)`.

Accepted incidents are rows with `valid=true`, `day <= current_day`, and `kind` listed in `policy.supported_incidents`. Process accepted rows by `(day, event_id)`. Ignored rows keep only `event_id`, `kind`, and `reason`, where reason is `invalid`, `future_day`, or `unsupported_kind`.

`budget_grant` adds `delta_pct` to the flag budget. `kill_switch` makes every segment for the flag state `killed` with zero percent. `force_state` with state `active` restores a row that was only blocked by dependency or lock. `dependency_waiver` removes one edge through its inclusive duration. `segment_lock` applies to the target segment and descendants through `duration_days` plus the gold lock grace. `segment_compromise` quarantines the target segment and descendants.

Dependency waves use active edges after waivers. Flags in a dependency cycle have `dependency_status=cycle_blocked` and `wave=null`. A flag depending on a killed flag has `dependency_status=upstream_killed`. Other flags are `ready`; their wave is zero for no active dependencies, otherwise one plus the maximum dependency wave.

Rollout row precedence is dependency block, segment lock, tier max percent cap, force active, kill switch, then segment compromise. Segment compromise is highest priority. Reasons are unique and sorted.

Exposure budgets sum observed users from every exposure file. For each flag, compute `budget_pct = tier.default_budget_pct + accepted grants`; `allowed_users` is the lower of `(total segment population * budget_pct) // 100` and the sum of rollout users allowed by effective percent. Status is `killed`, else `quarantine_exposure` when any observed row for the flag is in a compromised segment, else `over_budget` when observed exceeds allowed, else `within_budget`.

`summary.json` reports counts for total flags, total segments, applied incidents, ignored incidents, killed flags, cycle-blocked flags, quarantined segments, over-budget flags, and quarantine-exposure flags.
