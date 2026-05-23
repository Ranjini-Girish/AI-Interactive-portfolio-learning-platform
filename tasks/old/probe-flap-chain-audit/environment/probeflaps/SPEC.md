# Probe flap chain audit (normative)

All inputs are UTF-8 JSON. The audit day is `pool_state.current_day` (integer). Never mutate anything under `/app/probeflaps/`.

## Nodes

Each file `nodes/<node_id>.json` defines `node_id` (equals filename stem), `tier` ∈ {`gold`,`silver`,`bronze`}, `parent_id` (string or JSON null), `probes_by_day` (object mapping decimal day strings to exactly `ok`, `fail`, or `flap`), and optionally `tier_history` (array of objects with integer `as_of_day` and string `tier` ∈ {`gold`,`silver`,`bronze`}). Days absent from `probes_by_day` are ignored for flap transitions and fail counts.

## Effective tier

For each node, define the audit-day **effective tier** as follows:

1. Collect every `tier_history` entry whose `as_of_day <= current_day`.
2. If the collected set is non-empty, the effective tier is the `tier` field of the entry with the largest `as_of_day` (ties on `as_of_day` resolved by lexicographic order of `tier`, then keep the later of equal tiers).
3. If the collected set is empty (no `tier_history` entries, or every entry has `as_of_day > current_day`), the effective tier is the node’s static `tier` field.
4. A `tier_history` entry whose `tier` is not in {`gold`,`silver`,`bronze`} is ignored.

Every per-node threshold, soak length, and rolling window in the rest of this spec uses the effective tier — never the static `tier` field. The static `tier` field is still emitted on every node row (under key `tier`) and the effective tier is emitted under key `effective_tier`.

## Rolling window

Let `W0 = policy.rolling_window_days` (integer ≥ 1). Each tier `T` accumulates integer `delta` values from kept `rolling_span_delta` incidents targeting `T` into `rolling_span_delta_sum[T]`. Define `W[T] = max(1, W0 + rolling_span_delta_sum[T])`. Every node uses the window for its **effective tier** `Teff`: `window_start[Teff] = current_day - (W[Teff] - 1)`.

For a node with effective tier `Teff`, the inclusive window is every integer `d` with `window_start[Teff] <= d <= current_day`.

`raw_failures` counts window days where `probes_by_day` maps the decimal string of `d` to `fail`.

`raw_flap_transitions` counts integers `d` in the window where `d > window_start[Teff]`, both `d-1` and `d` have entries in `probes_by_day`, and the two probe values differ.

## Incidents

Read `incident_log.events`. Keep only events with `accepted == true` and `event.day <= current_day`. Sort kept events by ascending `(day, event_id)` and process in that order for additive tier deltas and directive flags. Supported `kind` values:

- `extend_soak_delta`: `target_tier` ∈ {`gold`,`silver`,`bronze`}, integer `delta`. Add `delta` to the running soak allowance for that tier (additive).
- `fail_threshold_delta`: `target_tier`, integer `delta`. Add to the running fail threshold for that tier (additive).
- `flap_threshold_delta`: `target_tier`, integer `delta`. Add to the running flap threshold for that tier (additive).
- `rolling_span_delta`: `target_tier`, integer `delta`. Add `delta` to the rolling-span accumulator for that tier (additive). The tier’s effective window length `W[T]` uses the sum of these deltas together with `W0` as defined above.
- `flap_day_suppress`: `node_id`, `days` (array of integers). For each `d` in `days`, if `d` is in that node’s effective-tier window, `d > window_start[Teff]`, both `d-1` and `d` have probe entries, and the values differ, subtract 1 from `raw_flap_transitions` (floor at 0; each matching `d` from this event subtracts at most once).
- `fail_day_suppress`: `node_id`, `days` (array of integers). For each `d` in `days`, if `d` is in that node’s effective-tier window and `probes_by_day` maps the decimal string of `d` to `fail`, mark `d` as a suppressed fail day for that node. Suppressed fail days are subtracted (floored at 0; each matching `d` from this event subtracts at most once) from `raw_failures` when forming `effective_failures`, and are excluded from the `last_fail_day` calculation below.
- `isolate_node`: `node_id`. After numeric work, that node’s `computed_status` must be `isolated` with `degraded` true and `reasons` containing `isolate_incident`.
- `force_unhealthy`: `node_id`. After numeric work, that node’s `computed_status` must be `unhealthy` with `degraded` true and `reasons` containing `force_unhealthy_incident`.

Unknown kinds or missing required fields: ignore the event.

## Tier effective thresholds

For tier `T`: `effective_fail_threshold = max(1, policy.fail_threshold_by_tier[T] + sum(fail_threshold_delta.delta))`, same pattern for flap threshold, and `effective_soak_days = max(0, policy.soak_days_by_tier[T] + sum(extend_soak_delta.delta))` (soak may be 0).

`effective_flap_transitions` starts at `raw_flap_transitions` after all `flap_day_suppress` subtractions (floored at 0). `effective_failures` starts at `raw_failures` after all `fail_day_suppress` subtractions (floored at 0).

`last_fail_day` is the maximum integer `d` in the effective-tier window such that `probes_by_day[str(d)] == "fail"` AND `d` is NOT a suppressed fail day for that node (per the `fail_day_suppress` rule above). If no such `d` exists, `last_fail_day` is JSON null. `suppressed_fail_days` is the sorted ascending array of distinct integer days that contributed to a `fail_day_suppress` subtraction for that node (the intersection of suppress-event days with both the window and the fail-marked probe days).

## Evaluation order

Build a forest from `parent_id` links (null roots). Emit nodes in ascending `node_id` order, but compute each node’s primary status only after its parent (if any) is computed. A missing parent file treats the parent as `healthy` with `degraded` false.

Primary status precedence (first match wins):

1. Kept `isolate_node` for this `node_id` → `isolated`, `degraded` true.
2. Kept `force_unhealthy` for this `node_id` → `unhealthy`, `degraded` true.
3. Parent exists and parent `degraded` is true → `inherited_degraded`, `degraded` true.
4. `effective_failures >= effective_fail_threshold` → `unhealthy`, `degraded` true.
5. `last_fail_day` is not null and `(current_day - last_fail_day) < effective_soak_days` → `soaking`, `degraded` false.
6. `effective_flap_transitions >= effective_flap_threshold` → `flapping`, `degraded` false.
7. Otherwise → `healthy`, `degraded` false.

## Cross-reference overlay

After every node’s primary status (rules 1–7 above) is fixed, evaluate the cross-reference overlay in a separate pass.

Read `links/cross_refs.json`. The file contains a single object with key `directed_pressure` mapping to an array of objects, each with string fields `from` and `to`. An edge `{from: A, to: B}` is **active** if both `A` and `B` resolve to node ids that have an emitted row, `A != B`, and node `A`’s primary `degraded` is `true`. Edges whose `from` or `to` is not a known node id, or whose `from == to`, are ignored. Edges from nodes with primary `degraded == false` are ignored (the source must be degraded for the edge to apply). Cross-reference pressure does **not** transit through intermediate nodes — it is single-hop only, evaluated against primary statuses.

For each node `B`, define `pressure_sources(B)` as the sorted ascending array of distinct node ids `A` such that an edge `{from: A, to: B}` is active.

If `pressure_sources(B)` is non-empty AND `B`’s primary status from rules 1–7 is `healthy`, then `B`’s `computed_status` becomes `cross_ref_pressured`, `degraded` stays `false`, and `reasons` is `["cross_ref_pressure"]`. Otherwise the primary status from rules 1–7 stands and the cross-reference overlay does **not** alter `B`’s `computed_status`, `degraded`, or `reasons`.

## Reasons array

When `computed_status` is `healthy`, emit `[]`.

Otherwise include every applicable literal (strictly increasing ASCII, unique):

- `cross_ref_pressure` on cross_ref_pressured (this reason appears only on nodes whose final `computed_status` is `cross_ref_pressured`).
- `flap_threshold_exceeded` on flapping.
- `force_unhealthy_incident` on forced unhealthy.
- `isolate_incident` on isolated.
- `parent_degraded_inheritance` on inherited_degraded.
- `soaking_period` on soaking.
- `threshold_exceeded` on unhealthy from rule 4 (evaluate numeric comparison even if force would have applied — force skips this tag).

## Outputs (six files under `/app/audit/`)

Canonical JSON: UTF-8, two-space indent, ASCII only, keys sorted lexicographically at every object depth, colon plus single space, no trailing spaces on lines, exactly one trailing newline at EOF.

### node_verdicts.json

- `nodes`: array sorted by ascending `node_id`. Each object: `node_id`, `tier` (the static tier from the node file), `effective_tier`, `parent_id` (string or null), `raw_failures`, `raw_flap_transitions`, `effective_failures`, `effective_flap_transitions`, `effective_fail_threshold`, `effective_flap_threshold`, `effective_soak_days`, `last_fail_day` (int or null), `suppressed_fail_days` (array of ints, sorted ascending, possibly empty), `computed_status`, `degraded` (bool), `reasons`. Threshold, soak, and window fields are taken from the effective-tier policy row.

### tier_policy.json

- `tiers`: object with exactly keys `bronze`, `gold`, `silver`. Each value: `assigned_nodes` (count of nodes whose effective tier equals this tier), `base_fail_threshold`, `base_flap_threshold`, `base_rolling_window_days`, `base_soak_days`, `effective_fail_threshold`, `effective_flap_threshold`, `effective_rolling_span_days`, `effective_soak_days`, `fail_delta_sum`, `flap_delta_sum`, `rolling_span_delta_sum`, `soak_delta_sum`.

### incident_journal.json

- `applied_events`: array of kept well-formed incidents, each object with `day`, `event_id`, `kind`, plus kind-specific optional fields (`delta`, `target_tier`, `days`, `node_id`). Keys sorted inside each object. Array sorted by `(day asc, event_id asc)`.

### dependency_touchpoints.json

- `parents`: map keyed by `parent_id` string sorted ascending; include only parents referenced by at least one node. Each value: `{ "child_nodes": [ node_id ... sorted asc ], "parent_status": string }` using the parent’s `computed_status` after evaluation (overlay-adjusted).

### cross_ref_overlay.json

- `pressured_nodes`: array sorted by ascending `node_id`. Includes exactly the nodes whose final `computed_status` is `cross_ref_pressured` (i.e. primary status was `healthy` and `pressure_sources` is non-empty). Each entry: `{ "node_id": ..., "pressure_sources": [ node_id ... sorted asc ] }`. If no node is cross_ref_pressured, emit `"pressured_nodes": []`.

### summary.json

Fields (sorted keys): `applied_incident_events`, `cross_ref_pressured_nodes`, `degraded_nodes`, `flapping_nodes`, `healthy_nodes`, `ignored_incident_events`, `inherited_degraded_nodes`, `isolated_nodes`, `nodes_total`, `soaking_nodes`, `unhealthy_nodes`.

Counts follow names. `ignored_incident_events` is total log events minus kept well-formed count (including rejected, future day, unknown kind, malformed). `degraded_nodes` counts nodes with `degraded` true.

## Input layout

Nodes live in `nodes/*.json`. Cross-reference edges live in `links/cross_refs.json`. Files under `ancillary/` and `registry/` are packaging metadata only; the audit algorithm does not read them.
