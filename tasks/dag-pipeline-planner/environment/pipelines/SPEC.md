# DAG Pipeline Planner — Output Contract

This file is part of the read-only input dataset under `/app/pipelines/`. It defines exactly how the six output JSON files at `/app/plan/` must be derived from the inputs. Every requirement in this file is binding.

## Inputs

The dataset under `/app/pipelines/` contains:

- `pool_state.json` — `{"current_day": <int>, "scheduler_version": "<str>"}`. `current_day` is the planning reference day; all `day` fields elsewhere are integers.
- `cluster.json` — global resource and tier configuration (described below).
- `consumers.json` — declared dependencies between pipelines (described below).
- `incident_log.json` — `{"events": [...]}` (described below).
- `pipelines/<pipeline>/manifest.json` — per-pipeline metadata.
- `pipelines/<pipeline>/jobs/<job>.json` — per-job declaration. The set of jobs in a pipeline is exactly the set of files in its `jobs/` directory; the set of pipelines is exactly the set of subdirectories of `pipelines/`.

`cluster.json` has the shape:

```
{
  "slots_per_resource_class": {"cpu_small": <int>, "cpu_large": <int>, "gpu": <int>},
  "impaired_slot_carve_out_per_class": {"cpu_small": <int>, "cpu_large": <int>, "gpu": <int>},
  "tier_priority_modifier_int": {"prod": <int>, "staging": <int>, "dev": <int>},
  "retry_penalty_minutes_per_tier": {"prod": <int>, "staging": <int>, "dev": <int>},
  "partial_block_sla_multiplier_pct_per_tier": {"prod": <int>, "staging": <int>, "dev": <int>},
  "degraded_sla_debit_per_upstream_quarantine": <int>,
  "wave_pressure_debit_per_burst": <int>,
  "critical_chain_debit_per_link": <int>
}
```

`tier_priority_modifier_int`, `retry_penalty_minutes_per_tier`, and `partial_block_sla_multiplier_pct_per_tier` are keyed by every tier value that any manifest may use. Each `partial_block_sla_multiplier_pct_per_tier[tier]` is a non-negative integer percentage applied to base SLA only when a pipeline's pipeline_status is `partial_resource_block` (see SLA evaluation). `degraded_sla_debit_per_upstream_quarantine`, `wave_pressure_debit_per_burst`, and `critical_chain_debit_per_link` are non-negative integers used by the SLA evaluation rules below. Each `slots_per_resource_class[c]` is a positive integer; `impaired_slot_carve_out_per_class` shares the same key set as `slots_per_resource_class` and each value is a non-negative integer carve-out used by the wave-partition rule below.

`consumers.json` is `{"edges": [{"producer": "<pipeline>", "consumer": "<pipeline>"}, ...]}`. The producer-to-consumer graph induced by these edges is guaranteed to be acyclic across the pipeline set.

`pipelines/<p>/manifest.json` is `{"name": "<str>", "tier": "prod"|"staging"|"dev", "sla_hours": <int>}`.

`pipelines/<p>/jobs/<j>.json` is `{"name": "<str>", "depends_on": ["<job>", ...], "runtime_minutes": <int>, "resource_class": "<str>", "retry_count": <int>, "base_priority": <int>}`.

## Incident-log filtering

An event of `incident_log.events` is **accepted** iff **all** of the following hold:

- `kind` is one of `"job_quarantine"`, `"sla_breach_grace"`, `"resource_pool_freeze"`.
- `day` is an integer and `day <= pool_state.current_day`.
- For `"job_quarantine"`: `pipeline` matches a known pipeline AND `job` matches a job within that pipeline AND `reason` is a non-empty string.
- For `"sla_breach_grace"`: `pipeline` matches a known pipeline AND `extension_minutes` is a non-negative integer.
- For `"resource_pool_freeze"`: `resource_class` is a key of `cluster.slots_per_resource_class` AND `duration_days` is a positive integer.

A `resource_pool_freeze` event is **active** iff `event.day <= pool_state.current_day <= event.day + event.duration_days - 1`. A pipeline is **quarantined** iff there is at least one accepted `job_quarantine` event for it, regardless of the event's `day`.

Every other event is silently ignored and counted in `summary.ignored_incident_events`.

## Cycle detection and topological order

For each pipeline, build its directed dependency graph from `depends_on`. If any cycle exists in this graph, the entire pipeline is **cyclic** (regardless of how many jobs participate in the cycle); every job's `phase` is set to `0`, `start_minute`/`end_minute` are `null`, and the job's `status` becomes `blocked_cycle`.

For an acyclic pipeline, compute the topological **phase** of each job as the longest dependency-chain length ending at that job (a job with no `depends_on` has phase `0`; a job that depends on jobs with phases `{1, 2}` has phase `3`).

Within a phase, `effective_priority` orders jobs (lower is higher priority), with ties broken by job name ascending.

A pipeline whose `pipeline_status` is `blocked_quarantine`, `degraded`, `partial_resource_block`, or `scheduled` keeps these computed `phase` values in `schedule_plan.json` exactly as derived from `depends_on`. Only `blocked_cycle` pipelines collapse every job's `phase` to `0` — `blocked_quarantine` does **not** zero phases.

## Effective priority

`effective_priority = base_priority * cluster.tier_priority_modifier_int[manifest.tier]` (an integer). When the pipeline's pipeline_status is `degraded` (see below), every job of that pipeline has `effective_priority` increased by `100` after the multiplication; the deboost applies even to jobs whose own status is `blocked_resource_freeze`.

## Quarantine and resource-block cascade

Compute the **quarantined set** as the set of pipelines with at least one accepted `job_quarantine` event.

A pipeline belongs to the **partial-resource-block set** iff it is not quarantined, not cyclic, and at least one of its jobs has status `blocked_resource_freeze` (per the per-job rule below — this includes jobs that are only indirectly frozen via same-pipeline `depends_on` propagation).

Compute the **degraded set** as the smallest set obtained by walking `consumers.edges` transitively from every pipeline in the union of the quarantined set and the partial-resource-block set: each direct consumer of a member is in the degraded set, every consumer-of-consumer is in the degraded set, and so on (producers are not). The quarantined set is **not** included in the degraded set — quarantined wins. A pipeline that is itself in the partial-resource-block set may also be in the degraded set when it is independently downstream of another quarantined or partial-resource-block pipeline; the pipeline_status precedence below resolves which label appears.

A pipeline's `pipeline_status` is determined by the first applicable rule in this order:

1. `"blocked_cycle"` — the pipeline has a cycle.
2. `"blocked_quarantine"` — the pipeline is in the quarantined set.
3. `"degraded"` — the pipeline is in the degraded set.
4. `"partial_resource_block"` — at least one job in this pipeline has status `blocked_resource_freeze`.
5. `"scheduled"` — none of the above.

A pipeline whose `pipeline_status` is `degraded` may still also satisfy condition 4; the degraded label wins (degraded jobs that are also resource-frozen are reported as `blocked_resource_freeze` per-job, but pipeline_status stays `degraded`).

## Per-job status

A job's `status` is determined by the first applicable rule in this order:

1. `"blocked_cycle"` — its pipeline has pipeline_status `blocked_cycle`.
2. `"blocked_quarantine"` — its pipeline has pipeline_status `blocked_quarantine`.
3. `"blocked_resource_freeze"` — **either** there is an active `resource_pool_freeze` event whose `resource_class` equals this job's `resource_class` (the job is *directly* frozen), **or** at least one job that this job transitively depends on (within the same pipeline, following `depends_on` edges) is itself `blocked_resource_freeze` by this same rule (the job is *indirectly* frozen). The freeze propagation walks downstream of every directly-frozen job along `depends_on` and applies regardless of the downstream job's own `resource_class`. Cross-pipeline `consumers.edges` do **not** propagate freezes.
4. `"degraded"` — its pipeline has pipeline_status `degraded`.
5. `"scheduled"` — none of the above.

## Effective runtime

Define `effective_runtime_minutes(j) = j.runtime_minutes + j.retry_count * cluster.retry_penalty_minutes_per_tier[j_pipeline.manifest.tier]` for every job, where `j_pipeline.manifest.tier` is the tier of the manifest of the pipeline that contains `j`. The retry penalty is per-tier: each retry attempt costs `cluster.retry_penalty_minutes_per_tier[tier]` extra minutes of capacity. The raw `runtime_minutes` field is **never** modified — it appears unchanged in `schedule_plan.json`. The `retry_count` field is **not** emitted in any output; it only enters the math through `effective_runtime_minutes`.

## Wave-based intra-phase scheduling

For pipelines with pipeline_status in `{blocked_cycle, blocked_quarantine}`, every job's `start_minute` and `end_minute` are `null`, the pipeline's `total_runtime_minutes` is `0`, and the pipeline emits no entry in `wave_plan.json`.

For every other pipeline (pipeline_status in `{scheduled, degraded, partial_resource_block}`), the schedule is computed phase by phase, and within each phase wave by wave per resource class.

The **impaired slot count** for a pipeline `P` and resource class `c` is

```
impaired_slots(P, c) = max(1, cluster.slots_per_resource_class[c]
                              - cluster.impaired_slot_carve_out_per_class[c])
                       if pipeline_status(P) in {degraded, partial_resource_block}
impaired_slots(P, c) = cluster.slots_per_resource_class[c]
                       if pipeline_status(P) == scheduled
```

The carve-out is per-pipeline-status, not per-job-status: a `degraded` pipeline uses the carved-out value for *every* resource class even when the per-class carve-out integer is zero (the result is just `slots_per_resource_class[c]` in that case). Carve-out always clamps at `1`, so a class with `slots_per_resource_class[c] == carve_out_per_class[c]` still has at least one slot.

For a phase `p` of such a pipeline, let `eligible(p)` be the set of jobs in phase `p` whose own status is not `"blocked_resource_freeze"`. Group `eligible(p)` by `resource_class`. For each resource class `c` that appears in `eligible(p)`:

1. Let `S = impaired_slots(P, c)`.
2. Sort the jobs of class `c` in phase `p` by `(effective_runtime_minutes desc, name asc)`. This is the **LPT order** for `(p, c)`.
3. Partition the LPT-ordered list into consecutive **waves** of at most `S` jobs each. Wave 0 contains positions `0..S-1`, wave 1 contains positions `S..2S-1`, and so on; the final wave may contain fewer than `S` jobs. The number of waves for `(p, c)` is `ceil(len / S)`.
4. `wave_duration(p, c, w) = max(effective_runtime_minutes(j) for j in wave w)`.
5. `class_runtime(p, c) = sum(wave_duration(p, c, w) for w in 0..number_of_waves)`.

Then:

- `phase_runtime(p) = max(class_runtime(p, c) for c in eligible(p)`); when `eligible(p)` is empty (every job in the phase is frozen, or the phase has no jobs at all) `phase_runtime(p) = 0`.
- `upstream_offset_minutes` is `0` when pipeline_status is `scheduled`. When pipeline_status is `degraded` or `partial_resource_block`, the offset is `max(total_runtime_minutes(P) for every transitive producer P of this pipeline whose pipeline_status is in {scheduled, degraded, partial_resource_block})`, or `0` if no such producer exists. Transitive producers are reached by walking `consumers.edges` in the producer direction (consumer→producer→producer-of-producer, …). Producers whose pipeline_status is `blocked_cycle` or `blocked_quarantine` contribute `0` and are therefore excluded from the max. Because `consumers.edges` is acyclic across pipelines, the offsets are well-defined and can be computed by a single producer-first topological pass.
- `phase_start(p) = upstream_offset_minutes + sum(phase_runtime(k) for k in 0..p-1)`.
- For a non-frozen job `j` in phase `p`, resource class `c`, occupying wave `w`:
  - `wave_offset(p, c, w) = sum(wave_duration(p, c, k) for k in 0..w-1)`.
  - `start_minute(j) = phase_start(p) + wave_offset(p, c, w)`.
  - `end_minute(j) = start_minute(j) + effective_runtime_minutes(j)`.
- A job whose own status is `"blocked_resource_freeze"` emits `start_minute = null` and `end_minute = null` and contributes `0` to its phase's runtime. Frozen jobs are not partitioned into any wave and are absent from `wave_plan.json`.
- `total_runtime_minutes = upstream_offset_minutes + sum(phase_runtime(p) for every phase p of the pipeline)`.

`upstream_offset_minutes` and `total_runtime_minutes` must be computed in producer-first order across the pipeline graph: a pipeline's totals depend on the totals of every transitive producer, so each pipeline is evaluated only after all of its transitive producers have been evaluated.

## Burst pressure

Define the **burst pressure** of a pipeline `P` as the number of `(phase, resource_class)` pairs in `P` whose number of non-frozen jobs **strictly exceeds** `cluster.slots_per_resource_class[resource_class]`. The threshold here is the un-carved installed capacity, not `impaired_slots(P, c)`: a "burst" measures demand against the cluster's installed slot count for the class, regardless of whether the pipeline's own wave partition was tightened by the impaired-slot carve-out. Frozen jobs are ignored. Pipelines whose pipeline_status is `blocked_cycle` or `blocked_quarantine` have `burst_pressure(P) = 0` by definition (no waves are computed for them).

For a `scheduled` pipeline `impaired_slots(P, c) == cluster.slots_per_resource_class[c]`, so the burst-pressure definition coincides with "wave count > 1". For a `degraded` or `partial_resource_block` pipeline whose carve-out is non-zero on `c`, a `(p, c)` with `slots_per_resource_class[c]` jobs of class `c` already produces multiple waves under the carved-out partition yet still does not contribute to `burst_pressure` because the un-carved slot count is not exceeded.

## Critical chain

The **critical-chain depth** of a pipeline `P`, written `critical_chain_depth(P)`, is the maximum number of consecutive consumer edges in any path that starts at `P` and walks `producer_to_consumer` edges (i.e., from a producer to one of its consumers) through pipelines whose pipeline_status is in `{scheduled, degraded, partial_resource_block}` only. Edges into a pipeline whose pipeline_status is `blocked_cycle` or `blocked_quarantine` are not traversed; such pipelines never appear as an interior or terminal node of the chain. The depth is `0` when `P` itself is blocked, and `0` when `P` has no non-blocked consumer.

Concretely, with `non_blocked = {Q : pipeline_status(Q) in {scheduled, degraded, partial_resource_block}}` and `consumers_of(Q) = {C : (Q, C) is an edge in consumers.edges}`,

```
critical_chain_depth(P) = 0                              if P not in non_blocked
critical_chain_depth(P) = 0                              if no consumer of P is in non_blocked
critical_chain_depth(P) = 1 + max(critical_chain_depth(C)
                                  for C in consumers_of(P) if C in non_blocked)
                                                          otherwise
```

Because `consumers.edges` is acyclic across the pipeline set, the max is well-defined and can be computed by a single consumer-first topological pass.

## SLA evaluation

`base_sla_minutes`:

- `0` if pipeline_status is `blocked_quarantine`.
- Otherwise, `manifest.sla_hours * 60` plus the sum of `extension_minutes` of every accepted `sla_breach_grace` event for this pipeline (regardless of those events' `day`).

A first SLA value `pre_sla_minutes` is computed by pipeline_status:

- `pre_sla_minutes = base_sla_minutes` if pipeline_status is `blocked_cycle`, `blocked_quarantine`, or `scheduled`.
- `pre_sla_minutes = (base_sla_minutes * cluster.partial_block_sla_multiplier_pct_per_tier[manifest.tier]) // 100` if pipeline_status is `partial_resource_block` (integer floor division; multiplier is a percentage).
- `pre_sla_minutes = max(0, base_sla_minutes - cluster.degraded_sla_debit_per_upstream_quarantine * len(upstream_quarantined))` if pipeline_status is `degraded`. Here `upstream_quarantined` is the same sorted list reported in `quarantine_status.json` for that pipeline (zero-length when no upstream is quarantined; a degraded pipeline reached only via a partial-resource-block upstream has `len(upstream_quarantined) == 0` and therefore an unmodified base SLA at this stage).

An intermediate `burst_sla_minutes` then folds in the burst-pressure debit:

- `burst_sla_minutes = pre_sla_minutes` if pipeline_status is `blocked_cycle` or `blocked_quarantine` (burst pressure is `0` for these and would not reduce anything anyway).
- `burst_sla_minutes = max(0, pre_sla_minutes - cluster.wave_pressure_debit_per_burst * burst_pressure(P))` for every other pipeline_status. The burst-pressure debit is applied **after** the partial-block multiplier and the upstream-quarantine debit, never instead of them, and is clamped at zero.

Finally `effective_sla_minutes` folds in the critical-chain debit:

- `effective_sla_minutes = burst_sla_minutes` if pipeline_status is `blocked_cycle` or `blocked_quarantine` (the chain debit is silently zero for these because `critical_chain_depth(P)` is `0` for blocked pipelines anyway, and SLA is vacuous for them — but `effective_sla_minutes` still equals `burst_sla_minutes`, not `pre_sla_minutes`).
- `effective_sla_minutes = max(0, burst_sla_minutes - cluster.critical_chain_debit_per_link * critical_chain_depth(P))` for every other pipeline_status. The critical-chain debit is applied **after** the burst-pressure debit, on top of every preceding rule (the partial-block multiplier or the upstream-quarantine debit, then the burst-pressure debit), and is clamped at zero.

The partial-block SLA tightening applies **only** to pipelines whose pipeline_status is exactly `partial_resource_block`. A `degraded` pipeline that also has some `blocked_resource_freeze` jobs uses the degraded debit rule, not the multiplier.

`sla_met`:

- `true` if pipeline_status is `blocked_cycle` or `blocked_quarantine` (vacuous).
- Otherwise, `total_runtime_minutes <= effective_sla_minutes`.

## Output schemas

All six outputs are written under `/app/plan/`. List ordering is part of the contract.

### `/app/plan/schedule_plan.json`

```
{"pipelines": [{"name": "<str>", "tier": "<str>", "pipeline_status": "<str>", "upstream_offset_minutes": <int>, "effective_sla_minutes": <int>, "total_runtime_minutes": <int>, "sla_met": <bool>, "jobs": [{"name": "<str>", "phase": <int>, "effective_priority": <int>, "resource_class": "<str>", "runtime_minutes": <int>, "start_minute": <int>|null, "end_minute": <int>|null, "status": "<str>"}]}]}
```

`pipelines` is sorted by `name` ascending. `jobs` is sorted by `(phase ascending, effective_priority ascending, name ascending)`. Each pipeline entry has exactly the eight documented keys; each job has exactly the eight documented keys.

### `/app/plan/cycle_report.json`

```
{"pipelines": [{"name": "<str>", "has_cycle": <bool>, "cycle_jobs": ["<str>", ...]}]}
```

`pipelines` is sorted by `name` ascending. For acyclic pipelines, `has_cycle` is `false` and `cycle_jobs` is `[]`. For cyclic pipelines, `cycle_jobs` is the sorted-ascending union of every job that participates in any cycle (computed by Tarjan-equivalent strongly-connected-component analysis: a job is in a cycle iff it is in an SCC of size ≥ 2 OR it has a self-loop in `depends_on`).

### `/app/plan/resource_utilization.json`

```
{"by_resource_class": [{"resource_class": "<str>", "slots_total": <int>, "minutes_demanded": <int>, "minutes_blocked_by_freeze": <int>, "active_freeze": <bool>}]}
```

`by_resource_class` is sorted by `resource_class` ascending and lists every key of `cluster.slots_per_resource_class`. `minutes_demanded` is the sum of the **raw** `runtime_minutes` (not `effective_runtime_minutes`) over every job whose pipeline_status is **not** in `{blocked_cycle, blocked_quarantine}` (so degraded and partial_resource_block contribute, but blocked pipelines do not). `minutes_blocked_by_freeze` is the sum of the **raw** `runtime_minutes` over every job whose own status is `blocked_resource_freeze` (whether directly or indirectly frozen per the per-job-status rule above), and is indexed by that downstream job's own `resource_class` (so an indirect freeze on a `cpu_small` job contributes to `cpu_small`, not to the upstream frozen class). `active_freeze` is `true` iff there is an active `resource_pool_freeze` event for this resource class at `pool_state.current_day`.

### `/app/plan/quarantine_status.json`

```
{"pipelines": [{"name": "<str>", "quarantine_state": "quarantined"|"degraded"|"normal", "quarantined_jobs": ["<str>", ...], "upstream_quarantined": ["<str>", ...]}]}
```

`pipelines` is sorted by `name` ascending. `quarantine_state` is `"quarantined"` for pipelines in the quarantined set, `"degraded"` for pipelines in the degraded set, and `"normal"` otherwise. `quarantined_jobs` is the sorted-ascending list of job names that are the target of an accepted `job_quarantine` event for that pipeline (empty for non-quarantined pipelines). `upstream_quarantined` is the sorted-ascending list of pipeline names that are quarantined and are reachable as transitive producers via `consumers.edges` (empty for non-degraded pipelines, and possibly empty for degraded pipelines reached only via a partial-resource-block upstream).

### `/app/plan/wave_plan.json`

```
{"pipelines": [{"name": "<str>", "burst_pressure": <int>, "phases": [{"phase": <int>, "resource_classes": [{"resource_class": "<str>", "waves": [{"wave_index": <int>, "duration_minutes": <int>, "jobs": ["<str>", ...]}]}]}]}]}
```

`wave_plan.json` reports, for every pipeline whose pipeline_status is in `{scheduled, degraded, partial_resource_block}`, the per-phase per-resource-class wave layout described in **Wave-based intra-phase scheduling**. Pipelines whose pipeline_status is `blocked_cycle` or `blocked_quarantine` are **omitted** from this file (they appear in every other output).

Sort and emission rules:

- `pipelines` is sorted by `name` ascending and contains exactly the non-blocked pipelines.
- Each pipeline's `burst_pressure` is the integer defined in **Burst pressure** (zero when no `(phase, resource_class)` exceeds its slot count).
- Each pipeline's `phases` is sorted by `phase` ascending. A phase that has zero non-frozen jobs (every job frozen, or the phase contains no jobs at all) is **omitted** entirely from the pipeline's `phases` list — it has no waves to describe.
- Each phase's `resource_classes` is sorted by `resource_class` ascending and contains exactly the resource classes that appear among that phase's non-frozen jobs.
- Each resource class's `waves` is sorted by `wave_index` ascending and contains every wave produced by the LPT-then-slot partition (wave 0, wave 1, …); the final wave may have fewer than `slots_per_resource_class[resource_class]` jobs but is still listed.
- `duration_minutes` of a wave is the wave's `wave_duration` (the max `effective_runtime_minutes` over the jobs in the wave).
- `jobs` within a wave is sorted by `name` **ascending** (the LPT order is used only to determine wave membership; the emitted list inside a wave is alphabetical for output stability).

### `/app/plan/summary.json`

```
{"current_day": <int>, "scheduler_version": "<str>", "total_pipelines": <int>, "total_jobs": <int>, "ignored_incident_events": <int>, "by_pipeline_status": {"scheduled": <int>, "degraded": <int>, "partial_resource_block": <int>, "blocked_quarantine": <int>, "blocked_cycle": <int>}, "by_job_status": {"scheduled": <int>, "degraded": <int>, "blocked_resource_freeze": <int>, "blocked_quarantine": <int>, "blocked_cycle": <int>}, "sla_violations": ["<pipeline>", ...], "burst_pressure_total": <int>}
```

`sla_violations` is sorted ascending and contains every pipeline whose `sla_met` is `false`. Every key in `by_pipeline_status` and `by_job_status` must appear with an integer value (zero if absent). `burst_pressure_total` is the sum of `burst_pressure(P)` over **every** pipeline (blocked pipelines contribute `0`).

## Canonical encoding

Every output JSON file is encoded with `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)` followed by exactly one trailing newline byte. Two correct implementations of this contract must produce byte-identical output for the same input. Do not modify any file under `/app/pipelines/` while computing the report.
