# Simulation Checkpoint Rollback Planner — Output Contract

This file is part of the read-only input dataset under `/app/runs/`. It defines exactly how the five output JSON files at `/app/plan/` must be derived from the inputs. Every requirement here is binding.

## Input layout

- `/app/runs/pool_state.json` — `{"current_day": <int>, "current_minute_of_day": <int>}`. `current_day` is the integer day-of-year used for every age comparison.
- `/app/runs/governance/policy.json` — central thresholds. Required fields: `residual_max`, `energy_drift_pct_max`, `samples_per_second_min`, `gpu_saturation_max`, `cost_approval_node_hours`, `peak_quiesce_window` (`{"start_day": <int>, "end_day": <int>}`), `peak_quiesce_surcharge_pct` (integer percent), `chronic_runs_threshold`, `chronic_runs_recent_days`, `volatility_ratio_threshold`, `trend_change_pct_threshold`, `severity_buckets` (object whose keys `minor`/`moderate`/`severe`/`critical` map to `{"max_violation_pct": <int>}` upper bounds; `critical` upper bound is `null`), `consumer_pause_max_hops` (positive integer), `exploratory_cost_discount_pct` (integer 0–100 inclusive).
- `/app/runs/dependencies.json` — `{"<upstream_sim>": ["<consumer_sim>", ...], ...}`. Keys are upstream producers; values are direct downstream consumers. A sim absent as a key has no consumers.
- `/app/runs/incident_log.json` — `{"events": [{"event_id": "...", "kind": "...", "day": <int>, "sim_id": "..."|null, "dataset_id": "..."|null}, ...]}`.
- `/app/runs/metrics/current_telemetry.json` — `{"telemetry": {"<sim_id>": {"residual_norm": <float>, "energy_drift_pct": <float>, "nan_count": <int>, "step_walltime_seconds": <float>, "gpu_util_percent": <float>, "nvram_mb": <int>, "samples_per_second": <float>}, ...}}`.
- `/app/runs/metrics/window_history.json` — `{"history": {"<sim_id>": [<sample>, ..., <sample>], ...}}` where each entry is exactly six samples chronologically (oldest first, newest last) carrying the same fields as current telemetry.
- `/app/runs/history/run_history.csv` — header `simulation,total_runs,total_rollbacks,last_rollback_day,avg_rollback_walltime_hours,avg_rollback_cost_node_hours`. `last_rollback_day` may be empty.
- `/app/runs/manifests/<sim_id>.json` — per-simulation manifest. Required fields: `sim_id`, `engine`, `kind` (one of `production`/`exploratory`), `current_checkpoint_step`, `last_known_good_step`, `started_at_day`, `stabilization_steps`, `inputs_dataset`. Optional `scheduled_quiesce_window`: `{"start_day": <int>, "end_day": <int>}`.

The set of all simulations is the union of `manifests/<sim_id>.json` filenames; `<sim_id>` from the filename must equal the `sim_id` field. A sim absent from `current_telemetry.json` or `window_history.json` is invalid and recorded only in `summary.invalid_simulations`.

## Incident-log filtering

An event is **accepted** iff `kind ∈ {corruption_confirmed, dataset_compromise, force_pin}`, `day <= pool_state.current_day`, and (when `kind != dataset_compromise`) `sim_id` matches some manifest, OR (when `kind == dataset_compromise`) `dataset_id` is non-empty. Every other event is silently ignored and counted in `summary.ignored_incident_events`.

## Twist 1 — Rollback eligibility gate (four-condition composition)

For each manifest sim S, evaluate the gates in this order. The first failing gate determines the skip label; later gates are not evaluated.

1. **violation** — at least one of: `residual_norm > residual_max`, `energy_drift_pct > energy_drift_pct_max`, `samples_per_second < samples_per_second_min`, `nan_count > 0`. If no violation holds, S is `healthy` (no rollback, no skip).
2. **capacity** — fail iff `gpu_util_percent > gpu_saturation_max`. Skip label: `skipped_capacity`.
3. **grace** — fail iff `current_checkpoint_step < stabilization_steps`. Skip label: `skipped_grace`.
4. **quiesce** — fail iff `current_day` falls within `[start_day, end_day]` (inclusive on both ends) of S's own `scheduled_quiesce_window` (when present). `policy.peak_quiesce_window` does **not** participate in this gate; it is consulted only for the cost surcharge. Skip label: `skipped_quiesce`.

If all four gates pass, S is `eligible` and gets a rollback plan entry. Skips are reported only in `summary.json` (per-label counters); they do **not** appear in `rollback_plan.json`.

## Twist 2 — Force-rollback override (NaN / corruption_confirmed)

A sim is **force-rolled** iff `nan_count > 0` OR there exists an accepted `corruption_confirmed` event for that `sim_id`. Force-roll re-evaluates Twist 1 as follows: the violation gate is treated as satisfied; the **grace** and **quiesce** gates are bypassed (force-roll ignores them); the **capacity** gate still applies (a force-rolled sim with `gpu_util > gpu_saturation_max` is still `skipped_capacity`).

For every force-rolled sim that survives the capacity gate, severity is forced to `critical`, strategy is forced to `full_restart`, and `rollback_to_step = last_known_good_step`. Force-roll does not by itself zero `rollback_to_step`; only Twist 4's compromise rule does.

## Twist 3 — Trend analysis (four states)

For every eligible (or force-rolled) sim, compute the trend on the **primary violated metric**:

- For each violated metric M let `violation_fraction(M)` be `(current(M) - threshold) / threshold` for `residual_norm` and `energy_drift_pct`, `(threshold - current(M)) / threshold` for `samples_per_second`. `nan_count` is excluded from the primary-metric pick (it has no continuous threshold). Pick the M with the largest `violation_fraction`. Ties: ASCII-smallest metric name.
- If there is no violated metric (e.g., a Twist 4 step 1 sim with healthy telemetry, or a force-rolled sim by `corruption_confirmed` only with `nan_count == 0`), pick `residual_norm`.
- Let `oldest = window_history[sim][0][M]` and `newest = current_telemetry[sim][M]`. Compute `change_pct = (newest - oldest) / oldest * 100` and **invert sign** when `M == "samples_per_second"`.
- Compute `volatility_ratio = stddev(window_history[sim][*][M]) / |mean(window_history[sim][*][M])|` using the population stddev.
- Classify in this strict precedence:
  1. `volatility_ratio > policy.volatility_ratio_threshold` → `volatile`.
  2. else `change_pct >= +policy.trend_change_pct_threshold` → `degrading`.
  3. else `change_pct <= -policy.trend_change_pct_threshold` → `improving`.
  4. else → `stable`.

`trend_report.json` carries one entry per eligible sim (including force-rolled): `{sim_id, primary_metric, oldest_value, current_value, change_pct, volatility_ratio, trend}` rounded to 4 decimals for floats.

## Twist 4 — Compromise + dependency cascade (cross-cutting override)

For every accepted `dataset_compromise` event with `dataset_id = D`:

1. Every sim S whose manifest has `inputs_dataset == D` is added to the rollback plan **regardless of telemetry** (even healthy sims, even sims that would have been skipped by Twist 1). The capacity gate **does not** apply here. For each such S: severity is `critical`, strategy is `full_restart`, `rollback_to_step = 0`, `reason` includes the substring `dataset_compromise:<D>`.
2. The set of **directly-compromised** sims from step 1 propagates through `dependencies.json` along directed producer → consumer edges. Compute the **shortest-path hop count** from any directly-compromised sim to every reachable consumer (each edge counts as one hop). A sim is added to `dependency_order.consumers_to_pause` iff its hop count is **at least 1** and **at most** `policy.consumer_pause_max_hops` (inclusive). Sort that list ASCII ascending. Directly-compromised sims themselves are never listed here.
3. Every sim that appears in the **final** `consumers_to_pause` list from step 2 and **also** has its own rollback entry (via Twist 1 or Twist 2) gets its severity bumped one bucket: `minor → moderate → severe → critical`. The bump is applied **after** Twist 1's severity is computed and **after** Twist 2's force-critical, so a force-critical entry stays `critical`.

A `force_pin` event for `sim_id = S` removes S from the rollback plan entirely (overrides every other rule, including dataset_compromise) and increments `summary.force_pinned_count`.

## Twist 5 — Canonical corruption_confirmed selection

When more than one accepted `corruption_confirmed` event references the same `sim_id`, choose the **canonical** event as follows: prefer the strictly larger `day`; if several tie on `day`, prefer the lexicographically smallest `event_id` string (a missing `event_id` field is treated as the empty string). Only the canonical event participates in force-roll detection and in the optional `safe_step` rollback override described under Severity.

## Twist 6 — Exploratory cost attenuation

After `estimated_cost_node_hours` has been computed with the peak-quiesce surcharge rule and rounded to two decimals, if the manifest's `kind` is `exploratory`, multiply by `(1 - policy.exploratory_cost_discount_pct / 100)` and round the product again to two decimals. Production sims skip this second multiplier. `manual_approval_required` compares the **final** `estimated_cost_node_hours` to `policy.cost_approval_node_hours`. `summary.total_estimated_cost_node_hours` sums the final per-plan costs.

## Severity, strategy, traffic, cost

Compute `max_violation_pct` over the violated metrics of an eligible sim using the formula in Twist 3, multiplied by 100 (sign already absolute). For force-rolled-only sims (no telemetry violation, just NaN-or-corruption) `max_violation_pct = 0` is used as the input.

Severity buckets are taken from `policy.severity_buckets`: assign the smallest bucket whose `max_violation_pct` upper bound is `>=` the computed value, evaluated in the order `minor`, `moderate`, `severe`, `critical`. Twist 2 forces `critical`. Twist 4 step 1 forces `critical`. Twist 4 step 3 bumps as defined.

Strategy and traffic share map directly from severity:

- `minor` → strategy `resume_in_place`, `traffic_share_percent = 10`
- `moderate` → strategy `fork_replicate`, `traffic_share_percent = 25`
- `severe` → strategy `full_restart`, `traffic_share_percent = 75`
- `critical` → strategy `full_restart`, `traffic_share_percent = 100`

`estimated_walltime_hours` is `avg_rollback_walltime_hours` from the CSV (default 4.0 if missing or invalid). `estimated_cost_node_hours` is `avg_rollback_cost_node_hours` from the CSV (default 50.0 if missing or invalid), then **multiplied** by `(1 + peak_quiesce_surcharge_pct / 100)` iff `current_day ∈ policy.peak_quiesce_window` (inclusive), then rounded to 2 decimals. If the manifest `kind` is `exploratory`, apply Twist 6's discount and round again to 2 decimals. `manual_approval_required` is `true` iff the final `estimated_cost_node_hours > policy.cost_approval_node_hours`.

`rollback_to_step` defaults to `last_known_good_step`; Twist 4 step 1 overrides to `0`; the canonical `corruption_confirmed` event from Twist 5, when it carries an explicit `safe_step` field, overrides to that integer.

## Output schemas (5 files under `/app/plan/`)

Every file is UTF-8, indented with two spaces, with object keys sorted ascending at every level, and ends in a single trailing newline.

### `/app/plan/rollback_plan.json`

```
{"plans": [{"sim_id": "...", "current_checkpoint_step": <int>, "rollback_to_step": <int>, "strategy": "...", "severity": "...", "traffic_share_percent": <int>, "reason": "...", "violated_metrics": ["..."], "dependency_warnings": ["..."], "trend": "...", "estimated_walltime_hours": <float>, "estimated_cost_node_hours": <float>, "manual_approval_required": <bool>}]}
```

`plans` is sorted by `sim_id` ascending. `violated_metrics` is sorted ASCII ascending; for Twist 4-only entries (healthy sim added by `dataset_compromise`) it is `[]`. `dependency_warnings` is the list of direct consumers of `sim_id` from `dependencies.json` (sorted ascending), or `[]`.

#### `reason` — exact contract

`reason` is a non-empty string built by joining ordered tokens with the literal two-character separator `"; "` (semicolon, space). Tokens are emitted in this **fixed order**, with no leading or trailing whitespace and no extra punctuation:

1. **One token per violated metric**, in ASCII-ascending order of the metric name (the same order as `violated_metrics`). For each metric `M` use the exact format:
   - `M == "energy_drift_pct"`  →  `energy_drift_pct=<current>>{policy.energy_drift_pct_max}`
   - `M == "nan_count"`         →  `nan_count=<current>>0`
   - `M == "residual_norm"`     →  `residual_norm=<current>>{policy.residual_max}`
   - `M == "samples_per_second"`→  `samples_per_second=<current><{policy.samples_per_second_min}`
   The value on the left of the comparator is the **raw** field as parsed from `current_telemetry.json` (no rounding); the value on the right is the **raw** policy threshold from `governance/policy.json`. Both numeric values are rendered with the implementation language's default short round-trip float-to-string representation — i.e. Python's `str(float)` / `f"{x}"` (so `0.02`, not `0.020`; `100.0`, not `100`; never scientific notation for in-range values). Use `<` only for `samples_per_second` (because the violation is "below the floor"); every other metric uses `>`. Integer telemetry fields (`nan_count`) render as plain integers (`nan_count=4>0`).
2. `dataset_compromise:<D>` — emitted iff Twist 4 step 1 applies, where `<D>` is the manifest's `inputs_dataset` string verbatim.
3. `corruption_confirmed` — emitted iff this sim has an accepted `corruption_confirmed` event (independently of whether `nan_count` also fires; both can show up in the same reason).
4. `forced_entry` — emitted **only** when none of the above tokens are present. This handles the rare degenerate case of a force-rolled sim with no telemetry violation, no NaN, and no compromise (it must still produce a non-empty reason).

The same metric tokens are also what populate `violated_metrics` (after the optional `nan_count` join), so `violated_metrics` and the metric-token prefix of `reason` always agree. The reason MUST contain the substring `dataset_compromise:<D>` whenever Twist 4 step 1 applies.

##### Examples

- A sim with only `residual_norm` over its threshold (raw value `0.245`, threshold `0.18`):
  `residual_norm=0.245>0.18`
- A sim with both `energy_drift_pct` (`8.7` vs cap `5.0`) and `samples_per_second` (`140.0` vs floor `220.0`):
  `energy_drift_pct=8.7>5.0; samples_per_second=140.0<220.0`
- A NaN-forced sim with `nan_count=4` and a corruption_confirmed event for it:
  `nan_count=4>0; corruption_confirmed`
- A directly-compromised, otherwise-healthy sim whose `inputs_dataset` is `dset_climate_v3`:
  `dataset_compromise:dset_climate_v3`
- A directly-compromised sim that is **also** corruption-forced and has `residual_norm` over threshold:
  `residual_norm=0.31>0.18; dataset_compromise:dset_climate_v3; corruption_confirmed`
- A force-rolled sim (corruption only, no NaN, no telemetry violation, not directly compromised):
  `corruption_confirmed`
- The fallback (no metrics, no compromise, no corruption — only reachable via a degenerate force path):
  `forced_entry`

### `/app/plan/trend_report.json`

```
{"trends": [{"sim_id": "...", "primary_metric": "...", "oldest_value": <float>, "current_value": <float>, "change_pct": <float>, "volatility_ratio": <float>, "trend": "..."}]}
```

`trends` is sorted by `sim_id` ascending and contains exactly the same set of `sim_id`s as `rollback_plan.json`.

### `/app/plan/dependency_order.json`

```
{"order": [{"rank": <int>, "sim_id": "...", "depends_on_upstream": ["..."]}], "consumers_to_pause": ["..."]}
```

`order` lists every sim that has a rollback entry, ranked by topological dependency-first traversal of `dependencies.json` restricted to the rollback set: a sim's `depends_on_upstream` is the list of rollback-set sims from which `sim_id` is reachable as a transitive consumer (sorted ascending). The rank ordering is: `len(depends_on_upstream)` ascending (upstream-most first), then `sim_id` ascending. Ranks are consecutive starting from 1. `consumers_to_pause` is the hop-bounded list from Twist 4 step 2 (sorted ASCII ascending).

### `/app/plan/chronic_runs.json`

```
{"chronic": [{"sim_id": "...", "total_rollbacks": <int>, "last_rollback_day": <int>, "days_since_last_rollback": <int>}]}
```

A sim is **chronic** iff its CSV row has `total_rollbacks >= policy.chronic_runs_threshold` AND `last_rollback_day` is a valid integer AND `pool_state.current_day - last_rollback_day <= policy.chronic_runs_recent_days`. Sorted by `sim_id` ascending.

### `/app/plan/summary.json`

```
{
  "current_day": <int>,
  "total_simulations_checked": <int>,
  "simulations_requiring_rollback": <int>,
  "simulations_healthy": <int>,
  "simulations_skipped_capacity": <int>,
  "simulations_skipped_grace": <int>,
  "simulations_skipped_quiesce": <int>,
  "invalid_simulations": ["..."],
  "force_pinned_count": <int>,
  "ignored_incident_events": <int>,
  "total_estimated_cost_node_hours": <float>,
  "manual_approvals_required": <int>,
  "dependency_chain_max_depth": <int>,
  "peak_quiesce_active": <bool>,
  "severity_breakdown": {"critical": <int>, "minor": <int>, "moderate": <int>, "severe": <int>}
}
```

`total_simulations_checked` is the number of manifest files. `simulations_healthy` is the count of sims with no telemetry violation and no Twist 4 entry. `total_estimated_cost_node_hours` is the sum across `rollback_plan.plans[*].estimated_cost_node_hours`, rounded to 2 decimals. `dependency_chain_max_depth` is the maximum value of `len(depends_on_upstream)` across `dependency_order.order`. `peak_quiesce_active` is `true` iff `current_day ∈ policy.peak_quiesce_window`. `severity_breakdown` keys are sorted ascending and tally the severity field across `rollback_plan.plans`.
