# Probe flap chain audit (normative)

All inputs are UTF-8 JSON. The audit day is `pool_state.current_day` (integer). Never mutate anything under `/app/probeflaps/`.

## Nodes

Each file `nodes/<node_id>.json` defines `node_id` (equals filename stem), `tier` ∈ {`gold`,`silver`,`bronze`}, `parent_id` (string or JSON null), and `probes_by_day` (object mapping decimal day strings to exactly `ok`, `fail`, or `flap`). Days absent from the map are ignored for flap transitions and fail counts.

## Rolling window

Let `W0 = policy.rolling_window_days` (integer ≥ 1). Each tier `T` accumulates integer `delta` values from kept `rolling_span_delta` incidents targeting `T` into `rolling_span_delta_sum[T]`. Define `W[T] = max(1, W0 + rolling_span_delta_sum[T])`. Every node uses the window for its own tier: `window_start[T] = current_day - (W[T] - 1)`.

For a node with tier `T`, the inclusive window is every integer `d` with `window_start[T] <= d <= current_day`.

`raw_failures` counts window days where `probes_by_day` maps the decimal string of `d` to `fail`.

`raw_flap_transitions` counts integers `d` in the window where `d > window_start[T]`, both `d-1` and `d` have entries in `probes_by_day`, and the two probe values differ.

`last_fail_day` is the maximum `d` in the window with probe `fail`, or JSON null if none.

## Incidents

Read `incident_log.events`. Keep only events with `accepted == true` and `event.day <= current_day`. Sort kept events by ascending `(day, event_id)` and process in that order for additive tier deltas and directive flags. Supported `kind` values:

- `extend_soak_delta`: `target_tier` ∈ {`gold`,`silver`,`bronze`}, integer `delta`. Add `delta` to running soak allowance for that tier (additive).
- `fail_threshold_delta`: `target_tier`, integer `delta`. Add to running fail threshold for that tier (additive).
- `flap_threshold_delta`: `target_tier`, integer `delta`. Add to running flap threshold for that tier (additive).
- `rolling_span_delta`: `target_tier`, integer `delta`. Add `delta` to the rolling-span accumulator for that tier (additive). The tier’s effective window length `W[T]` uses the sum of these deltas together with `W0` as defined above.
- `flap_day_suppress`: `node_id`, `days` (array of integers). For each `d` in `days`, if `d` is in that node’s tier window, `d > window_start[T]`, both `d-1` and `d` have probe entries, and the values differ, subtract 1 from `raw_flap_transitions` (floor at 0; each matching `d` from this event subtracts at most once).
- `fail_day_suppress`: `node_id`, `days` (array of integers). For each `d` in `days`, if `d` is in that node’s tier window and `probes_by_day` maps the decimal string of `d` to `fail`, subtract 1 from `raw_failures` when forming `effective_failures` (floor at 0; each matching `d` from this event subtracts at most once).
- `isolate_node`: `node_id`. After numeric work, that node’s `computed_status` must be `isolated` with `degraded` true and `reasons` containing `isolate_incident`.
- `force_unhealthy`: `node_id`. After numeric work, that node’s `computed_status` must be `unhealthy` with `degraded` true and `reasons` containing `force_unhealthy_incident`.

Unknown kinds or missing required fields: ignore the event.

## Tier effective thresholds

For tier `T`: `effective_fail_threshold = max(1, policy.fail_threshold_by_tier[T] + sum(fail_threshold_delta.delta))`, same pattern for flap threshold, and `effective_soak_days = max(0, policy.soak_days_by_tier[T] + sum(extend_soak_delta.delta))` (soak may be 0).

`effective_flap_transitions` starts at `raw_flap_transitions` after all `flap_day_suppress` subtractions (floored at 0). `effective_failures` starts at `raw_failures` after all `fail_day_suppress` subtractions (floored at 0).

## Evaluation order

Build a forest from `parent_id` links (null roots). Emit nodes in ascending `node_id` order, but compute each node’s status only after its parent (if any) is computed. A missing parent file treats the parent as `healthy` with `degraded` false.

Status precedence (first match wins):

1. Kept `isolate_node` for this `node_id` → `isolated`, `degraded` true.
2. Kept `force_unhealthy` for this `node_id` → `unhealthy`, `degraded` true.
3. Parent exists and parent `degraded` is true → `inherited_degraded`, `degraded` true.
4. `effective_failures >= effective_fail_threshold` → `unhealthy`, `degraded` true.
5. `last_fail_day` is not null and `(current_day - last_fail_day) < effective_soak_days` → `soaking`, `degraded` false.
6. `effective_flap_transitions >= effective_flap_threshold` → `flapping`, `degraded` false.
7. Otherwise → `healthy`, `degraded` false.

## Reasons array

When `computed_status` is `healthy`, emit `[]`.

Otherwise include every applicable literal (strictly increasing ASCII, unique):

- `force_unhealthy_incident` on forced unhealthy.
- `isolate_incident` on isolated.
- `parent_degraded_inheritance` on inherited_degraded.
- `threshold_exceeded` on unhealthy from rule 4 (evaluate numeric comparison even if force would have applied — force skips this tag).
- `soaking_period` on soaking.
- `flap_threshold_exceeded` on flapping.

## Outputs (five files under `/app/audit/`)

Canonical JSON: UTF-8, two-space indent, ASCII only, keys sorted lexicographically at every object depth, colon plus single space, no trailing spaces on lines, exactly one trailing newline at EOF.

### node_verdicts.json

- `nodes`: array sorted by ascending `node_id`. Each object: `node_id`, `tier`, `parent_id` (string or null), `raw_failures`, `raw_flap_transitions`, `effective_failures`, `effective_flap_transitions`, `effective_fail_threshold`, `effective_flap_threshold`, `effective_soak_days`, `last_fail_day` (int or null), `computed_status`, `degraded` (bool), `reasons`.

### tier_policy.json

- `tiers`: object with exactly keys `bronze`, `gold`, `silver`. Each value: `base_fail_threshold`, `base_flap_threshold`, `base_rolling_window_days`, `base_soak_days`, `effective_fail_threshold`, `effective_flap_threshold`, `effective_rolling_span_days`, `effective_soak_days`, `fail_delta_sum`, `flap_delta_sum`, `rolling_span_delta_sum`, `soak_delta_sum`.

### incident_journal.json

- `applied_events`: array of kept well-formed incidents, each object with `day`, `event_id`, `kind`, plus kind-specific optional fields (`delta`, `target_tier`, `days`, `node_id`). Keys sorted inside each object. Array sorted by `(day asc, event_id asc)`.

### dependency_touchpoints.json

- `parents`: map keyed by `parent_id` string sorted ascending; include only parents referenced by at least one node. Each value: `{ "child_nodes": [ node_id ... sorted asc ], "parent_status": string }` using the parent’s computed status after evaluation.

### summary.json

Fields (sorted keys): `applied_incident_events`, `degraded_nodes`, `flapping_nodes`, `healthy_nodes`, `ignored_incident_events`, `inherited_degraded_nodes`, `isolated_nodes`, `nodes_total`, `soaking_nodes`, `unhealthy_nodes`.

Counts follow names. `ignored_incident_events` is total log events minus kept well-formed count (including rejected, future day, unknown kind, malformed). `degraded_nodes` counts nodes with `degraded` true.

## Input layout

Nodes live in `nodes/*.json`. Files under `ancillary/`, `registry/`, and `links/` are packaging metadata only; the audit algorithm does not read them.
