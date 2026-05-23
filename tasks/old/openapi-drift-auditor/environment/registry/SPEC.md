# OpenAPI Drift Auditor Specification

Normative contract: inputs, diff vocabulary, classifications, consumer impact,
migration phases, risk, and canonical JSON for five outputs under `/app/audit/`.

## Normative literals (read first)

- Any endpoint targeted by an **accepted** `force_break` incident has
  `classification` = `breaking_forced` and `reason` = **`forced_event`** (this
  exact string, not a change_kind name).
- **`cyclic_field_exposure`** uses the **same** `blocked_cycle` service set as
  migration planning (SCC on consumer→producer edges from `direct_field_reads`,
  plus the closure rule below). Do **not** infer cycles only from ad hoc
  field-exposure walk stacks.

## Inputs (under `/app/registry/`)

- `pool_state.json` — `{ "current_day": int }`.
- `policy/policy.json` — `freeze_extension_phases` (int), `tier_weights`
  (`gold`/`silver`/`bronze` → int), `supported_incident_kinds` (sorted ASCII).
- `consumers/dependencies.json` — `direct_field_reads` and `field_exposures`
  (schemas below).
- `incidents/incident_log.json` — `{ "events": [ ... ] }`.
- `services/<service_id>.json` and `baselines/<service_id>.json` — same
  `service_id` set; contract: `service_id`, `tier`, `auth_mode`, `endpoints[]`
  with `endpoint_id`, `params[]` (`name`, `type`, `required`), `response_fields[]`
  (`name`, `type`), `status_codes[]` (ints).

`direct_field_reads[*]` = `{consumer_id, producer_id, endpoint_id, fields}` with
sorted `fields`. `field_exposures[*]` = `{exposing_service, producer_id, endpoint_id,
field_map}` — keys are producer field names, values names in the exposing response.

Events: `{event_id, kind, service_id, endpoint_id, day, accepted}`; `endpoint_id`
may be `""` for `consumer_freeze`.

## Diff vocabulary (per endpoint)

Compare current vs baseline per `endpoint_id`. Emit ASCII-sorted `change_kinds`
from: `auth_mode_changed`, `endpoint_added`, `endpoint_removed`,
`param_added_optional`, `param_added_required`, `param_removed`,
`param_required_added`, `param_type_narrowed`, `response_field_added`,
`response_field_removed`, `response_field_type_changed`, `status_code_class_change`.
Removed endpoints: only `endpoint_removed`. Added: only `endpoint_added`.
`status_code_class_change`: sets of HTTP class digits (status/100) differ between
current and baseline for that endpoint.

## Tier-graded classification (per endpoint)

For each `change_kind`, tier strength:

| change_kind | gold | silver | bronze |
|---|---|---|---|
| auth_mode_changed | breaking | breaking | breaking |
| endpoint_added | non_breaking | non_breaking | non_breaking |
| endpoint_removed | breaking | breaking | breaking |
| param_added_optional | minor | minor | minor |
| param_added_required | breaking | minor | minor |
| param_removed | breaking | consumer_aware | minor |
| param_required_added | breaking | breaking | minor |
| param_type_narrowed | breaking | breaking | minor |
| response_field_added | non_breaking | non_breaking | non_breaking |
| response_field_removed | breaking | consumer_aware | minor |
| response_field_type_changed | breaking | consumer_aware | minor |
| status_code_class_change | breaking | minor | minor |

`consumer_aware` → `breaking` if some `direct_field_reads` row references this
endpoint and (for response-field changes) lists the changed field in `fields`;
else `minor`. Endpoint classification = strongest kind with precedence
`breaking > minor > non_breaking`. Empty `change_kinds` → `non_breaking`,
`reason` = `no_changes`. Else `reason` = ASCII-smallest `change_kind` whose
tier-resolved strength equals the chosen classification.

## Incident events

**Accepted** iff `accepted`, `day <= current_day`, `kind` in
`supported_incident_kinds`, and duplicate winner per `(kind, service_id,
endpoint_id)`: largest `day`, then ASCII-smallest `event_id`. Others **ignored**.
Kinds: `force_break` (pair `(service_id, endpoint_id)`), `consumer_freeze`
(`endpoint_id` must be `""`).

## Force-break override

For each accepted `force_break` target endpoint: `classification` =
`breaking_forced`, `reason` = `forced_event`; every direct or transitive reader of
that endpoint gets `impact_type` = `force_migration_required`, `hop_distance` = 1,
`cause_field` = `""`; producer service migration `phase` = 0,
`phase_origin` = `forced_phase_zero`; risk `action` = `block`,
`action_origin` = `forced_event`.

## Blocked-cycle set B (shared)

Directed graph: edge `a → b` for each `direct_field_reads` row with
`consumer_id` = a, `producer_id` = b. Run SCC (Tarjan/Kosaraju). Mark nodes in
any SCC with size > 1, or with a self-edge `a → a`, as **core**. Then repeatedly:
if node `s` is not marked and has any outgoing edge to a marked node, mark `s`.
The final marked set is **B** — the same set that receives migration
`phase_origin` = `blocked_cycle` (phase -1) in Migration plan below.

## Consumer impact

For endpoints classified `breaking` or `breaking_forced`, propagate from each
`(producer, endpoint, field)` that drove the strongest `breaking` classification:

1. **Direct readers** — `direct_field_reads` rows for that endpoint: include
   when the changed field is listed in `fields`, or for endpoint-level triggers
   (`endpoint_removed`, `param_removed`, forced) any reader. Assign
   `affected_direct`, `hop_distance` = 1, `cause_field` = ASCII-smallest changed
   field or `""`.
2. **Field exposures** — for rows matching `(producer_id, endpoint_id)` where the
   changed producer field is a key in `field_map`, continue to consumers of
   `(exposing_service, field_map[field])` with `affected_transitive`,
   `hop_distance` ≥ 2, chaining exposures whose `producer_id` is the prior hop’s
   exposing service.
3. **Cyclic field exposure** — whenever step 1 or 2 would assign an impact to a
   reader `c` for producer `p` and endpoint `e`, if `c ∈ B` and (`p ∈ B` or
   `p == c`), assign `cyclic_field_exposure` instead for that
   `(c, p, e)` triple, with `hop_distance` = 0 and `cause_field` carried from the
   breaking trigger (ASCII-smallest field when several). For a `breaking` endpoint
   on producer `sid`, if any direct reader `r` has `r ∈ B` and `sid ∈ B`, emit
   `cyclic_field_exposure` for those `(r, sid, endpoint)` rows and **skip** the
   normal direct/transitive walk for that endpoint’s breaking propagation (the
   force-break override still replaces entries derived from forced endpoints).
4. **Force-break** entries override per the Force-break override section.

Aggregate per consumer: one row per `(producer_service, endpoint_id)`; strongest
`impact_type` with precedence `force_migration_required` >
`cyclic_field_exposure` > `affected_direct` > `affected_transitive`; smallest
positive `hop_distance` among winners (`cyclic` keeps 0). `summary_action`:
`force_migrate` if any `force_migration_required`; else `migrate` if any
`affected_direct` and tier gold/silver; else `monitor` if any `affected_direct`
(bronze), `affected_transitive`, or `cyclic_field_exposure`; else `none`. Every
`consumer_id` appearing in `direct_field_reads` appears in `consumer_impact.json`
(even with empty `impacted_endpoints`).

## Migration plan

Topological phase: `phase(s) = 0` if no producer edges else `1 + max(effective
phase of producers))` on the same graph as B. Apply in decreasing precedence:
(1) accepted `force_break` on service → phase 0, `forced_phase_zero`; (2) `s ∈ B`
→ phase -1, `blocked_cycle`; (3) accepted `consumer_freeze` →
`topological_phase + freeze_extension_phases`, `deferred_freeze`; (4) else topo
phase, `topo`. Sort `services` by phase asc, tier rank desc (gold 3, silver 2,
bronze 1), `service_id` asc.

## Risk assessment

Per service: `breaking_count` = endpoints in `{breaking, breaking_forced}`;
`minor_count`, `non_breaking_count`; `risk_score` = `breaking_count * tier_weight
+ minor_count`; `affected_consumer_count` = distinct consumers with any
`impacted_endpoints` row for this producer. `action`: force_break on service →
`block`; else breaking>0 and tier gold/silver → `block`; else breaking>0 bronze
→ `warn`; else minor>0 → `warn`; else `allow`. `action_origin`: `forced_event`
if from force_break else `tier_rule`. Sort services by `service_id`.

## Output schemas

**change_classification.json** — `{services:[{service_id,tier,endpoint_changes:[{
endpoint_id,change_kinds[],classification,reason,affected_consumer_count}]}]}`.
Sort services and `endpoint_changes` by id; `change_kinds` sorted.

**consumer_impact.json** — `{consumers:[{consumer_id,tier,summary_action,
impacted_endpoints:[{producer_service,endpoint_id,impact_type,hop_distance,
cause_field}]}]}`. Sort consumers; impacts by `(producer_service, endpoint_id)`.
`impact_type` ∈ `affected_direct|affected_transitive|force_migration_required|
cyclic_field_exposure`. `summary_action` ∈ `force_migrate|migrate|monitor|none`.

**migration_plan.json** — `{services:[{service_id,tier,phase,phase_origin}]}`.
`phase_origin` ∈ `forced_phase_zero|blocked_cycle|deferred_freeze|topo`.

**risk_assessment.json** — `{services:[{service_id,tier,risk_score,breaking_count,
minor_count,non_breaking_count,affected_consumer_count,action,action_origin}]}`.

**summary.json** — single object, keys exactly (ASCII sorted on disk):
`accepted_incident_events`, `affected_direct_count`, `affected_transitive_count`,
`allow_action_services_count`, `block_action_services_count`,
`blocked_cycle_services_count`, `breaking_count`, `breaking_forced_count`,
`consumers_total`, `consumers_with_no_impact`, `cyclic_consumers_count`,
`deferred_services_count`, `endpoint_changes_total`,
`force_migration_required_count`, `force_phase_zero_count`,
`ignored_incident_events`, `minor_count`, `non_breaking_count`, `services_total`,
`warn_action_services_count`. All non-negative integers.

## Canonical JSON

UTF-8, two-space indent, sorted object keys at every depth, exactly one trailing
newline (`\n`).
