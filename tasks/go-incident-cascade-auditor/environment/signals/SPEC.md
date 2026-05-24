# Go Incident Cascade Auditor - Output Contract

This read-only dataset lives under `/app/signals/`. Produce five JSON outputs under `/app/report/` exactly as defined here.

## Input layout

- `pool_state.json` has `{ "current_minute": int }`.
- `policy/triage_policy.json` has per-tier threshold objects with integer keys: `warning_error_pct`, `critical_error_pct`, `warning_p95_ms`, `critical_p95_ms`, `warning_qps_drop_pct`, `critical_qps_drop_pct`.
- `services/<service_id>.json` has `{ service_id, node_id, team, tier, dependencies }`. `tier` is one of `gold`, `silver`, `bronze`. `dependencies` is a list of service IDs this service calls.
- `metrics/<service_id>.json` has `{ service_id, windows }`, where `windows` is a minute-sorted list of objects with keys `{ minute, error_pct, p95_ms, qps }`.
- `oncall/rotations.json` has `{ "teams": { "<team>": { "primary": str, "secondary": str } } }`.
- `incidents/incident_log.json` has `{ "events": [ ... ] }`.

## Incident acceptance and ordering

An incident is accepted when all are true:

1. `accepted == true`
2. `minute <= current_minute`
3. `kind` is one of `node_quarantine`, `throttle_window`, `severity_override`
4. Kind-specific fields are valid

Kind-specific validation:

- `node_quarantine`: requires known `node_id`, integer `from_minute`, integer `to_minute`, and `from_minute <= to_minute`.
- `throttle_window`: requires known `service_id`, integer `start_minute`, integer `end_minute`, positive integer `extra_error_pct`, and `start_minute <= end_minute`.
- `severity_override`: requires known `service_id` and `severity` in `healthy`, `warning`, `critical`.

Accepted incidents are processed in `(minute asc, event_id ASCII asc)` order. Rejected incidents only affect `summary.ignored_incident_events`.

Active windows at runtime:

- A `node_quarantine` is active when `from_minute <= current_minute <= to_minute`.
- A `throttle_window` is active when `start_minute <= current_minute <= end_minute`.

When multiple accepted `severity_override` incidents target the same service, only the last one in processing order applies.

## Severity derivation

For each service, read the last metric window as `latest`; previous windows are all earlier entries.

1. Start with `effective_error_pct = latest.error_pct`.
2. Add every active throttle's `extra_error_pct` for this service.
3. Compute `baseline_qps` as integer floor of the arithmetic mean of all previous windows' `qps`. If there are no previous windows, use `latest.qps`.
4. Compute `qps_drop_pct`:
   - `0` when `baseline_qps <= 0`
   - otherwise `max(0, floor(100 * (baseline_qps - latest.qps) / baseline_qps))`
5. Determine `base_severity` using tier thresholds:
   - `critical` if any critical threshold is met (`effective_error_pct`, `latest.p95_ms`, or `qps_drop_pct`)
   - else `warning` if any warning threshold is met
   - else `healthy`

## Propagation and precedence

Build reverse dependency edges from every service list.

- Every service with `base_severity == critical` is a propagation root.
- A root propagates `warning` to every transitive reverse dependent.
- If a service already has `critical`, propagation does not change it.
- If a service is `healthy`, propagation raises it to `warning`.

After propagation:

1. Active node quarantine raises any `healthy` service on that node to `warning`.
2. The final override for that service, if present, sets `final_severity` exactly to the override value.

Reason precedence in `anomaly_report`:

- include all applicable reason tokens, deduplicate, and sort ASCII.
- tokens are `local_signal`, `propagated_from:<root_id>`, `node_quarantine`, `override`.
- add `local_signal` when `base_severity` is `warning` or `critical`.

## Outputs and encoding

Write UTF-8 JSON using `json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"`.

1. `anomaly_report.json` -> `{ "services": [...] }` sorted by `service_id`, each entry:
   `{ service_id, node_id, team, tier, base_severity, final_severity, qps_drop_pct, active_incidents, reasons }`
   - `active_incidents` sorted ASCII
   - `reasons` sorted ASCII
2. `blast_radius.json` -> `{ "roots": [...] }` sorted by `service_id`, each entry:
   `{ service_id, impacted_services, total_impacted }`
   - `impacted_services` are transitive reverse dependents of that root with `final_severity != healthy`, sorted ASCII
3. `paging_plan.json` -> `{ "pages": [...] }` sorted by `(priority, service_id)` where priority order is `p1 < p2 < p3`. Entry fields:
   `{ service_id, team, pager, backup_pager, priority }`
   - include only services with `final_severity != healthy`
   - `p1` for `critical`, `p2` for `warning` with `local_signal` or `override`, else `p3`
4. `node_health.json` -> `{ "nodes": [...] }` sorted by `node_id`, each entry:
   `{ node_id, services, status, critical_services }`
   - `services` sorted ASCII
   - `critical_services` sorted ASCII from services on node with `final_severity == critical`
   - status values:
     - `quarantined_hotspot` when quarantine active and critical_services not empty
     - `quarantined` when quarantine active only
     - `hotspot` when critical_services not empty only
     - `healthy` otherwise
5. `summary.json` is a flat object with integer keys:
   `services_total`, `services_healthy`, `services_warning`, `services_critical`, `propagated_services`, `quarantined_nodes`, `hotspot_nodes`, `quarantined_hotspot_nodes`, `accepted_incident_events`, `ignored_incident_events`, `p1_pages`, `p2_pages`, `p3_pages`.
