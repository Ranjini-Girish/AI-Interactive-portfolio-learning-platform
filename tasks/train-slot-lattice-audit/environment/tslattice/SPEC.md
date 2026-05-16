# Train slot lattice — normative specification

This document is authoritative for parsing, ordering, incident interactions, and JSON shape. The workspace prompt names deliverables and paths; every tie-break, filter, and canonicalization rule lives here.

## Paths

All inputs are rooted at `/app/tslattice/`. The bundled tree must not be modified at runtime. Only `/app/audit/` may be created when missing.

Environment variables: when `TSL_DATA_DIR` is set to a non-empty string, it replaces `/app/tslattice/` as the input root. When `TSL_AUDIT_DIR` is set to a non-empty string, it replaces `/app/audit/` as the output directory.

## Input files

- `pool_state.json` contains integer fields `current_day` (inclusive horizon) and `cluster_slot_cap` (non-negative integer baseline cluster capacity).
- `policy.json` contains `rung_precedence`, a JSON array of distinct strings listing rung names from highest privilege (index zero) to lowest. It also contains `tie_break`, a JSON array whose elements are drawn from the fixed vocabulary `tenant_weight_desc` and `run_id_asc`, each at most once, together listing the full tie-break chain after rung ordering.
- `index.json` contains two keys, `tenant_files` and `request_files`, each a JSON array of relative paths (strings) under the input root. Preserve the listed order only where this document explicitly says to use it; all emitted arrays that aggregate global results must follow the sorting rules below.
- Each file listed under `tenant_files` is a JSON object with string `tenant_id` (unique across tenants) and integer `weight` (may be zero or negative; used only for tie-breaking as specified).
- Each file listed under `request_files` is a JSON object with string fields `run_id` (unique across requests), `tenant_id`, `rung` (string), integer `submit_day`, integer `slots_asked` (non-negative), and either JSON null `depends_on` or a string `depends_on` equal to some other `run_id`.
- `incidents.json` contains key `events`, a JSON array of objects. Each object has integer `seq` (unique, positive), integer `day`, string `kind`, and optional fields depending on `kind`. Kinds used in this edition are `freeze_tenant`, `rung_override`, and `cap_trim`. For `freeze_tenant`, string `tenant_id` is required. For `rung_override`, string `run_id` and string `new_rung` are required. For `cap_trim`, integer `cluster_slot_cap` is required and must be non-negative.

## Incident semantics

Consider only incidents whose `day` is less than or equal to `pool_state.current_day`. Sort those incidents by ascending `seq` and process in that order to build auxiliary state:

1. Start with an empty map of rung overrides and with effective capacity equal to `pool_state.cluster_slot_cap`.
2. On `rung_override`, record `run_id` maps to `new_rung` (later events overwrite earlier ones for the same `run_id`).
3. On `cap_trim`, replace the effective capacity with the incident’s `cluster_slot_cap` (later `cap_trim` events overwrite earlier ones regardless of `day`, still subject to the filter in the first sentence of this section).
4. On `freeze_tenant`, record that `tenant_id` becomes frozen from `day` onward (inclusive). If multiple freezes exist for the same tenant, the smallest `day` wins.

After processing, a request is **frozen-blocked** when its `tenant_id` matches a frozen tenant and `submit_day` is greater than or equal to that tenant’s frozen-start day.

Apply `rung_override` values after freezes are known but before dependency analysis: for allocation ordering, each request’s rung string is the override if present, otherwise the request file’s `rung`.

## Dependency graph

Build a directed edge `depends_on -> run_id` whenever `depends_on` is a non-null string. Self-loops count as cycles. Run a standard strongly-connected-components decomposition on the subgraph induced by requests whose `run_id` appears as either a vertex or a target of an edge. Any component with more than one distinct vertex, or any single-vertex component whose sole vertex has a self-loop edge, marks every `run_id` in that component as **cycle-bound**. Collect the set `C` of all cycle-bound run ids. Emit `cycle_groups` as follows: partition `C` into components; sort each component’s ids ascending by UTF-8 byte string; sort the list of groups by comparing the first id of each group (ascending), then second, and so on.

A request is **dependency-feasible** when every `depends_on` chain eventually ends at null without passing through a missing `run_id` and without visiting any id in `C`. If `depends_on` references an unknown `run_id`, treat that request as not dependency-feasible and mark it with reason `unknown_dependency` during output emission (it still participates in cycle detection if edges among known ids form a cycle). For known ids only: if the target lies in `C`, the request is **blocked-by-cycle** unless it is itself in `C` (cycle-bound requests use reason `cycle`).

## Eligibility for slot competition

A request is **eligible** when `submit_day` is less than or equal to `pool_state.current_day`, it is dependency-feasible, it is not cycle-bound, it is not blocked-by-cycle, and it is not frozen-blocked.

## Allocation order and granting

Let `R` be the list of all eligible requests. Sort `R` by:

1. Ascending index of the request’s effective rung inside `policy.rung_precedence` (missing rung names sort after every known name by treating the index as positive infinity and breaking ties with rung string ascending UTF-8 bytes).
2. For each tie-break token in `policy.tie_break` in listed order: if `tenant_weight_desc`, sort by descending tenant `weight`, then ascending `tenant_id` UTF-8 bytes when weights tie; if `run_id_asc`, sort by ascending `run_id` UTF-8 bytes.

After this sort, walk the list once from start to end maintaining integer `remaining` initialized to the effective capacity after incidents. For each request in order:

- If `depends_on` is non-null, the predecessor run must already have been visited earlier in this same walk with `granted_slots` strictly greater than zero. If not, emit `granted_slots` zero with `denied_reason` string `blocked_dependency`.
- Otherwise, if `remaining` is zero, emit `granted_slots` zero with `denied_reason` string `saturated`.
- Otherwise let `g` be the lesser of `slots_asked` and `remaining`. Emit `g` with null `denied_reason`, then decrease `remaining` by `g`.

Every ineligible request must appear in the allocation output with `granted_slots` zero and `denied_reason` one of: `cycle` (cycle-bound), `blocked_dependency` (blocked-by-cycle or missing dependency closure), `unknown_dependency` (missing `depends_on` target), `frozen_tenant` (frozen-blocked), `not_submitted` (`submit_day` greater than `current_day`). Sort keys inside each object as required globally.

Non-eligible requests that are neither cycle-bound nor blocked-by-cycle nor unknown_dependency nor frozen nor future-submitted are impossible in this dataset; if encountered, use `not_submitted` for consistency.

Emit allocation rows sorted by ascending `run_id` UTF-8 bytes in the final JSON array `allocations` inside `allocation_plan.json`.

Each row within the allocations must contain exactly the following four fields: `run_id`, `tenant_id`, `granted_slots`, `denied_reason`.

## Incident trace output

For every incident in the original `events` array sorted by ascending `seq`, emit an object with keys `seq`, `applied` (boolean true when `day` is less than or equal to `current_day`), and `note` (short ASCII string: `ok` when applied, `future` when not applied because the day is beyond the horizon).

## Tenant utilization

For each tenant id observed in any request file, emit totals: `slots_granted` sum of `granted_slots` for that tenant in the allocation pass, `requests_served` count of requests with that tenant where `granted_slots` is positive, `requests_denied` count where `granted_slots` is zero and `denied_reason` is not null. Sort tenant keys ascending UTF-8 bytes in the emitted object.

## Summary

Emit integer counts: `requests_total`, `eligible_total`, `cycle_bound_total`, `granted_positive_total`, `incidents_seen_total` (length of `events`), `incidents_applied_total` (count with applied true in the trace).

## Canonical JSON

Every output file must be UTF-8 without a byte order mark. Serialize with Python semantics equivalent to `json.dumps(obj, sort_keys=True, indent=2, separators=(",", ": "))` and append a single newline (`\n`) after the closing brace or bracket. No trailing spaces are permitted beyond the single newline terminator.

## Output artifacts

Write exactly these five files under the audit directory: `allocation_plan.json`, `dependency_graph.json`, `incident_trace.json`, `tenant_utilization.json`, `summary.json`.

### `dependency_graph.json`

Keys: `cycle_groups` (array of sorted string arrays as defined), `known_run_ids` (sorted ascending unique ids from all request files), `edges` (array of objects `{ "from": depends_on, "to": run_id }` for every non-null depends_on, sorted by ascending `from` UTF-8 bytes then ascending `to`).

### `allocation_plan.json`

Key `allocations`: array of rows, each with exactly `run_id`, `tenant_id`, `granted_slots`, and `denied_reason` as defined above, sorted by ascending `run_id`.

### `incident_trace.json`

Key `events`: array of `{seq, applied, note}` sorted ascending by `seq`.

### `tenant_utilization.json`

Key `tenants`: object as defined.

### `summary.json`

Keys only as listed in the Summary section plus `effective_cluster_slot_cap` (integer after incidents).
