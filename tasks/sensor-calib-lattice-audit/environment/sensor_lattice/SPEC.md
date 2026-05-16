Sensor calibration lattice contract.

All input files are UTF-8 JSON unless noted. The current day is `pool_state.current_day`. Read labs from `labs/*.json`, batches from `batches/*.json`, sensors from `sensors/*.json`, and incident events from `incident_log.json`.

Each sensor names one batch, one tier, measured and reference ppm values, uncertainty ppm, and zero or more parent sensors in `depends_on`. A batch names its lab and day. A lab declares daily capacity units and signed bias ppm. Tier rules in `policy.json` define residual threshold, uncertainty threshold, recall days, capacity weight, and priority rank.

An incident is usable only when `accepted` is true, `day <= current_day`, and `kind` is one of `batch_contamination`, `lab_freeze`, `recall_extend`, or `sensor_suppress`. For duplicate usable events with the same kind and target, keep the latest day, then ASCII-largest event_id. All other events are ignored.

Contamination seeds are sensors whose batch is named by a kept `batch_contamination` event. Contamination propagates from each seed to every transitive descendant through `depends_on`. A sensor that belongs to any dependency cycle has lineage status `cyclic`; otherwise contaminated seeds and descendants are `tainted`, suppressed sensors are `suppressed`, and the rest are `clean`. Taint source is the ASCII-smallest nearest seed; hops is the shortest descendant distance.

For every sensor, `residual_ppm = abs(measured_ppm - reference_ppm)`. `adjusted_residual_ppm = abs(measured_ppm + lab.bias_ppm - reference_ppm)`. Recall age is `current_day - batch.day`. A kept `recall_extend` event adds `extra_days` to sensors of the targeted tier before recall state is decided.

Sensor status precedence is strict: `suppressed`, then `quarantined` for lineage `tainted` or `cyclic`, then `lab_frozen` when a kept `lab_freeze` covers the lab on current_day, then capacity placement, then `recall_due`, then `needs_review`, then `accepted`. Capacity placement applies only to sensors not already suppressed, quarantined, or frozen. Candidates are sorted by tier priority rank ascending, adjusted residual descending, uncertainty descending, then sensor_id ascending. A candidate consumes its tier capacity weight from its lab. If insufficient capacity remains, status is `capacity_deferred`; otherwise the candidate is placed and then classified as `recall_due` when age exceeds effective recall days, `needs_review` when adjusted residual exceeds the tier residual threshold or uncertainty exceeds the tier uncertainty threshold, and `accepted` otherwise.

Write exactly five files under the output directory. `calibration_plan.json` has `generated_day` and `sensors`, sorted by sensor_id. Each row has `sensor_id`, `tier`, `lab_id`, `batch_id`, `residual_ppm`, `adjusted_residual_ppm`, `uncertainty_ppm`, `status`, `decision_reason`, and `capacity_rank` where null is used for unplaced sensors.

`lineage_risk.json` has `sensors`, sorted by sensor_id, with `sensor_id`, `lineage_status`, `taint_source`, `taint_hops`, and `cycle_members`. Null is used when no taint source or hop exists.

`recall_windows.json` has `sensors`, sorted by sensor_id, with `sensor_id`, `age_days`, `effective_recall_days`, and `recall_state`. Recall state is `suppressed`, `quarantined`, `due`, or `current` under the same suppression/quarantine precedence.

`lab_ledger.json` has `labs`, an object keyed by lab_id. Each value has `base_capacity`, `capacity_used`, `capacity_remaining`, `frozen`, `placed_sensors`, and `deferred_sensors`. Sensor lists are sorted by sensor_id.

`summary.json` has integer fields: `sensors_total`, `accepted_sensors`, `needs_review_sensors`, `recall_due_sensors`, `capacity_deferred_sensors`, `lab_frozen_sensors`, `quarantined_sensors`, `suppressed_sensors`, `cyclic_sensors`, `applied_incident_events`, and `ignored_incident_events`.

JSON must be canonical: UTF-8, sorted object keys, two-space indentation, and a trailing newline.
