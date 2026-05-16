# Cryostat lattice readout audit

All inputs live under the read-only dataset root `/app/cryostat/`. Do not modify, rename, or remove anything below this tree.

## `/app/cryostat/pool_state.json`

Object fields:

- `as_of_day` — integer calendar day used as an upper bound when selecting readings and when evaluating incidents.
- `tol_millic_primary` and `tol_millic_secondary` — non-negative integer tolerances applied as half-widths around each sensor's nominal millikelvin band; tier `primary` uses the primary tolerance, every other tier value uses the secondary tolerance.
- `drift_grace_days` — non-negative integer; when the gap between a sensor's chosen `reading_day` and its `last_calibration_day` exceeds this value, calibration drift is added to the working temperature (see "Working temperature" below).
- `drift_per_day` — non-negative integer; per-day millikelvin drift added beyond the grace window.
- `recent_window_k` — positive integer K used by the chosen-reading aggregation rule below.
- `overlay` — optional object with boolean `active`, integer `add_millic`, and array `sensor_ids` of strings. When `active` is true, every sensor whose id appears in `sensor_ids` gains `add_millic` on its working temperature after linear conversion, after any applicable `rig_warm` offset, and after any applicable calibration drift, and before relaxation and range checks.

## `/app/cryostat/calibration/linear.json`

Object with integer fields `a` and `b`. For an integer ADC value `adc`, the linear millikelvin value is the integer `a * adc + b`.

## `/app/cryostat/thermal/edges.json`

Root value is a JSON array of objects with string fields `u`, `v`, and positive integer `w`. Each object is an undirected edge between sensor ids `u` and `v`. For every edge object, normalise endpoints so that `a = min(u, v)` and `b = max(u, v)` under ASCII string comparison; the canonical edge tuple is `(a, b, w)`. Process edges in ascending lexicographic order of `(a, b)` everywhere they appear.

## `/app/cryostat/readings/readings.json`

Array of objects with string `sensor_id`, integer `day`, and integer `adc`.

## `/app/cryostat/incidents/incident_log.json`

Array of objects, each with string `kind`, integer `day`, and boolean `accepted`. Additional fields by `kind`:

- `strap_quench` — includes string `strap_id`. When `accepted` is true and `as_of_day >= day`, every sensor with that `strap_id` receives verdict `strap_quenched` unless a higher-precedence verdict applies.
- `rig_warm` — includes string `rig_id` and integer `delta_millic`. When `accepted` is true and `as_of_day >= day`, for a sensor with the same `rig_id` whose chosen `reading_day >= day`, add `delta_millic` after the linear conversion and before calibration drift. Apply matching incidents in array order; the same incident may not be applied twice.
- `lattice_fault` — includes non-empty string array `seed_sensors`. When `accepted` is true and `as_of_day >= day`, form the undirected graph from `/app/cryostat/thermal/edges.json` over the set of all sensor ids that appear in any file under `/app/cryostat/sensors/`. Every sensor in the same connected component as any seed id that exists in the registry receives verdict `lattice_faulted` unless a higher-precedence verdict applies.

## Sensor records

Each file `/app/cryostat/sensors/<id>.json` contains string `sensor_id`, `strap_id`, `rig_id`, string `tier` (`primary` or `secondary`), integers `commissioned_day` and `last_calibration_day`, and array `nominal_range_millic` `[low, high]` with `low <= high`.

## Chosen reading (aggregation with rejection)

For each sensor, take the rows in `/app/cryostat/readings/readings.json` whose `sensor_id` matches and whose `day` satisfies `commissioned_day <= day <= as_of_day`. Reject every candidate whose `adc <= 0`. If no candidates survive rejection, the sensor has no chosen reading.

Otherwise sort the surviving candidates by `(day desc, adc desc)`, take the first K rows where `K = recent_window_k`, and aggregate them as follows:

- The chosen ADC is the median of the kept ADC values, computed by sorting the kept ADC values ascending and taking the middle element when K is odd, or the integer floor of `(low_mid + high_mid) / 2` (where `low_mid` and `high_mid` are the two middle elements) when K is even. Use floor division toward negative infinity.
- The chosen `reading_day` is the maximum `day` among the kept rows.

## Working temperature before relaxation

If there is no chosen reading, skip temperature work for that sensor. Otherwise, with the chosen ADC and `reading_day` from the previous step:

1. Compute `T = a * chosen_adc + b` using `a` and `b` from `/app/cryostat/calibration/linear.json`. All arithmetic is integer.
2. For each `rig_warm` incident in `/app/cryostat/incidents/incident_log.json` in file order, if it is `accepted`, `as_of_day >= incident.day`, the sensor's `rig_id` equals `incident.rig_id`, and `reading_day >= incident.day`, add `delta_millic` to `T`.
3. Calibration drift: let `gap = reading_day - last_calibration_day`. If `gap > drift_grace_days`, add `drift_per_day * (gap - drift_grace_days)` to `T`. Otherwise add nothing.
4. If `overlay.active` is true and the sensor id is listed in `overlay.sensor_ids`, add `overlay.add_millic` to `T`.

## Relaxation with verdict-aware edge freezing

Sensors with a chosen reading participate in relaxation. Initialise the working map `T[sid]` from the post-overlay values above. Run exactly three rounds, indexed `R = 1, 2, 3`. In each round, iterate edges in ascending `(a, b)` lexicographic order from the canonical edge list and apply, for each edge whose endpoints both appear in the working map:

`T[b] = T[b] + (effective_w * (T[a] - T[b])) // 1000`

where `//` denotes floor division toward negative infinity (so that `(-840) // 1000 = -1`, not `0`). The effective weight is determined as follows:

- In round 1, `effective_w = w` for every edge. No sensor is considered frozen in round 1.
- In rounds 2 and 3, evaluate the freeze status of each participating sensor at the **end of the previous round**: a sensor is frozen for round `R` (with `R in {2, 3}`) if its `T[sid]` after all of round `R - 1`'s edge updates is strictly below `low - tol` or strictly above `high + tol`, using its own `nominal_range_millic` and its tier-appropriate tolerance. For each edge in round `R`, if either endpoint `a` or `b` is frozen for round `R`, then `effective_w = 0` (the formula adds zero to `T[b]`). Otherwise `effective_w = w`.

Freeze status is recomputed once per round transition from the just-completed round's final temperatures; do not reclassify mid-round when intermediate edge updates push a sensor across its band. After three rounds, `T[sid]` holds the relaxed millikelvin value used for range checks.

## Range check

For tier `primary`, the tolerance is `tol_millic_primary`. For any other tier value, the tolerance is `tol_millic_secondary`. A sensor is **in range** when `low - tol <= T <= high + tol` for its own `nominal_range_millic`, using its relaxed `T`.

## Verdict precedence

Exactly one verdict string per sensor; the first matching rule wins:

1. `lattice_faulted` — sensor sits in a connected component touched by a qualifying `lattice_fault` incident, as defined above.
2. `strap_quenched` — sensor's `strap_id` matches a qualifying `strap_quench` incident.
3. `precommission` — at least one row in `/app/cryostat/readings/readings.json` carries this `sensor_id`, but no candidate satisfies `commissioned_day <= day <= as_of_day` (rejection of `adc <= 0` does not count as "no candidate" for this rule — there must be no in-window row before rejection is even considered).
4. `missing_read` — no chosen reading and rules 1–3 do not apply.
5. `stale_calibration` — chosen reading exists and `reading_day < last_calibration_day`.
6. `out_of_range` — chosen reading exists, rule 5 does not apply, and the relaxed temperature is not in range.
7. `ok` — otherwise.

## Reasons tags

Each verdict row carries a sorted unique string array `reasons` assembled from:

- The literal verdict name (always included).
- `overlay` when overlay millikelvin were applied to that sensor.
- `calib_drift` when calibration drift contributed any non-zero amount to the working temperature.
- For each applied `rig_warm` that increased that sensor's `T`, `rig_warm:<rig_id>:<day>` with the integer `day` from the incident.
- `lattice_fault:<day>` for every accepted `lattice_fault` whose connected component contains the sensor.
- `strap_quench:<day>` whenever the sensor's `strap_id` matches an accepted `strap_quench` incident, regardless of which verdict actually wins precedence.

## Outputs under `/app/audit/`

Write UTF-8 JSON with two-space indentation, sorted object keys at every depth, and exactly one trailing newline per file. Environment overrides: `CLR_DATA_DIR` defaults to `/app/cryostat`; `CLR_AUDIT_DIR` defaults to `/app/audit`.

1. `/app/audit/sensor_verdicts.json` — key `verdicts`: array of objects sorted by `sensor_id`. Each object has fields `sensor_id`, `strap_id`, `rig_id`, `tier`, `verdict`, `reading_day` (integer or null when no chosen reading), `relaxed_millic` (integer or null when no chosen reading), and `reasons` (sorted unique strings as defined above).
2. `/app/audit/thermal_relaxed.json` — key `temps`: object mapping each sensor id with a chosen reading to its relaxed integer temperature after three rounds; sorted keys.
3. `/app/audit/incident_touch.json` — key `touches`: array sorted by `sensor_id`, each `{ "sensor_id", "marks" }` where `marks` is sorted and lists `overlay` when overlay millikelvin were applied to that sensor; `calib_drift` when calibration drift contributed; `rig_warm:<rig_id>:<day>` for each accepted `rig_warm` that increased that sensor's temperature; `lattice_fault:<day>` for each accepted `lattice_fault` whose component contains that sensor; and `strap_quench:<day>` when that sensor's `strap_id` matches an accepted `strap_quench` incident's `strap_id`.
4. `/app/audit/summary.json` — keys `as_of_day`, `sensor_count`, `verdict_counts` (object mapping each verdict string that occurs among sensors to its count; keys sorted), `relax_rounds` fixed integer `3`, `edge_count` (number of edge objects in `/app/cryostat/thermal/edges.json` after canonical normalisation), `reading_rows` (length of the readings array in `/app/cryostat/readings/readings.json` before any rejection).

Canonical hash checks in tests serialise each fragment with sorted object keys, the compact separators `,` and `:` (no whitespace), no escaping of non-ASCII characters, and append a single newline before hashing.
