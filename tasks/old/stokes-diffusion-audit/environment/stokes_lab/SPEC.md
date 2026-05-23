# Stokes diffusion audit — normative contract

All JSON emitted under `/app/audit/` must be UTF-8, end with exactly one newline, use two-space indentation, and sort object keys lexicographically at every depth. Arrays follow the sort orders stated below. Numbers are JSON numbers. Use `null` only where this document explicitly allows it.

## Physical constants

Use IEEE binary64 arithmetic throughout intermediate steps. Boltzmann constant `k_B` = `1.380649e-23` (exact string value in joules per kelvin). Use `π` as `math.Pi` in implementations; numeric value is `3.14159265358979323846` truncated only by the host float width.

Dynamic viscosity `η` is taken in centipoise (`cP`) from the solvent tables and converted to pascal-seconds with `η_Pa_s = η_cP * 1e-3`. Hydrodynamic radius uses `r_m = r_nm * 1e-9` where `r_nm` is the measurement’s `hydrodynamic_radius_nm`.

The Stokes–Einstein diffusion coefficient in SI is `D_SI = (k_B * T_eff) / (6 * π * η_Pa_s * r_m)` when all inputs are valid for computation, using `r_m` from the clamped `r_nm` after the floor and ceiling steps. Emit `d_stokes_nm2_per_s` as `D_SI * 1e18` when the entry status is `ok`; otherwise emit JSON `null` for that field.

Round every emitted non-null `d_stokes_nm2_per_s` to six fractional digits using IEEE 754 round-half-to-even on the scaled value (multiply by `1e6`, apply half-even rounding to the nearest integer, divide by `1e6`).

## Ignored inputs

Any file or directory under `/app/stokes_lab/meta/` is human metadata and must not influence outputs. Parsers must not traverse it for business logic.

## Read-only inputs

- `/app/stokes_lab/pool_state.json` contains number `kelvin_offset_global` (may be negative); optional numbers `radius_floor_nm` and `radius_ceiling_nm` used only for the hydrodynamic radius clamp described later; optional number `drift_cap_K` (strictly positive when present) used to symmetrically cap summed sensor drift; and optional integer `stiction_lookback_days` (positive when present) used for the probe-stiction lower day bound described later. When both radius bounds are present and `radius_floor_nm` is strictly greater than `radius_ceiling_nm`, swap them before any clamping step.
- `/app/stokes_lab/incident_log.json` contains array `events` in file order. Each event has string `event_id`, string `kind`, boolean `accepted` (default `true` when absent), integer `day`, optional string `probe_id`, optional string `solvent_id`, optional number `delta_K`. For `bench_correction` events, `probe_id` and numeric `delta_K` are required whenever the event is evaluated; `solvent_id` may be absent or the empty string to mean a wildcard that matches every measurement solvent for the same probe.
- `/app/stokes_lab/solvents/*.json` each describe one solvent: string `solvent_id`, array `viscosity_points` of objects with number `temp_K`, number `viscosity_cP`. Points must be sorted strictly ascending by `temp_K` within the file.
- `/app/stokes_lab/probes/*.json` each contain string `probe_id` plus an optional pair of fields `chain_id` (string) and `chain_role` (one of the strings `"primary"` or `"secondary"`) that together describe the bench-chain relationship used by the propagation rule below. Either both fields are present or neither is; an unrelated `label` and any other opaque fields are ignored by processors. A probe whose `chain_role` is absent, empty, or any value other than `"primary"` / `"secondary"` is treated as belonging to no chain even when `chain_id` is present.
- `/app/stokes_lab/measurements/*.json` each contain exactly one measurement object with keys: string `measurement_id`, string `probe_id`, string `solvent_id`, string `solute_id`, number `hydrodynamic_radius_nm`, number `temp_reported_K`, integer `run_day`.

## Incident acceptance

An event is **accepted** when `accepted` is not boolean `false` and `kind` is one of `sensor_drift`, `probe_stiction`, `solvent_recall`, `bench_correction`, `recall_lift`, or `recall_relift`.

Increment `ignored_incident_events` once for each event in the original `events` array when any of the following holds: `accepted` is boolean `false`; `kind` is not exactly one of the six kinds named above; an accepted `sensor_drift` lacks numeric `delta_K`; an accepted `sensor_drift` lacks `probe_id` or references a `probe_id` not present among the measurement corpus; an accepted `probe_stiction` lacks `probe_id` or references a `probe_id` not present among the measurement corpus; an accepted `solvent_recall` lacks `solvent_id` or references a `solvent_id` not present among the measurement corpus; an accepted `bench_correction` lacks numeric `delta_K`; an accepted `bench_correction` lacks `probe_id` or references a `probe_id` not present among the measurement corpus; an accepted `bench_correction` carries a non-empty `solvent_id` that is not present among the solvent catalogue files; an accepted `recall_lift` lacks `solvent_id` or references a `solvent_id` not present among the solvent catalogue files; an accepted `recall_lift` carries a non-empty `probe_id` that is not present among the measurement-corpus probe set; an accepted `recall_relift` lacks `solvent_id` or references a `solvent_id` not present among the solvent catalogue files; an accepted `recall_relift` carries a non-empty `probe_id` that is not present among the measurement-corpus probe set. Events that increment this counter are excluded from drift summation, bench correction selection, recall lift evaluation, recall relift evaluation, chain propagation, and from `anomalies.json`.

## Sensor drift window summation

An accepted `sensor_drift` is **eligible** for a measurement when the event is not ignored, `probe_id` equals the measurement’s `probe_id`, and `event.day` lies within the closed integer window `[measurement.run_day - 6, measurement.run_day]` (a seven-day window inclusive at both ends). The raw drift sum for the measurement is `delta_drift_raw = sum of event.delta_K` over **every** eligible drift event for that measurement; the empty sum is `0`. There is no greatest-day winner: every eligible event contributes its full `delta_K` regardless of position in the array.

When `drift_cap_K` is present in `pool_state.json`, replace the raw sum with `delta_drift = sign(delta_drift_raw) * min(|delta_drift_raw|, drift_cap_K)` when `delta_drift_raw` is not bitwise zero in IEEE binary64; otherwise `delta_drift = 0`. When `drift_cap_K` is absent, `delta_drift = delta_drift_raw`. Increment `drift_capped_count` once for each measurement row when `drift_cap_K` is present and `|delta_drift_raw|` is strictly greater than `drift_cap_K`.

For each measurement, collect the unordered set of eligible drift `event_id` values; this set is the measurement’s **drift contributors** (membership is determined before capping; capping does not remove identifiers from the set).

## Bench correction selection

An accepted `bench_correction` is **eligible** for a measurement when the event is not ignored, `probe_id` equals the measurement’s `probe_id`, `event.day <= measurement.run_day` (no lower bound), and either the event’s `solvent_id` is absent, the empty string, or exactly equals the measurement’s `solvent_id`.

Let `R_floor` be the maximum `event.day` among accepted non-ignored `solvent_recall` events whose `solvent_id` equals the measurement’s `solvent_id` and whose `event.day <= measurement.run_day`. When no such recall exists, `R_floor` is undefined and the floor filter below is skipped.

Among eligible bench corrections for that measurement, discard any whose `event.day <= R_floor` when `R_floor` is defined. From the remaining candidates (which may be empty), select the single event with the greatest `day`; tie-break by later position in the `events` array (file order wins). Let `delta_bench` be that event’s `delta_K` when such an event exists, otherwise `0`. The bench rule is single-winner and is not summed.

## Probe stiction (direct and chain-propagated)

An accepted `probe_stiction` is **directly active** for a measurement when the event is not ignored, `probe_id` equals the measurement’s `probe_id`, `event.day <= measurement.run_day`, and either `stiction_lookback_days` is absent from `pool_state.json` or `event.day >= measurement.run_day - stiction_lookback_days` (inclusive lower bound on the same integer day line as the drift window).

A second activation path arises when the stiction event’s probe carries `chain_role == "primary"` and a non-empty `chain_id`. Such an event is **chain-propagated** to a measurement when the event is not ignored, `event.day <= measurement.run_day`, the measurement’s probe has the same `chain_id` as the event’s probe and `chain_role == "secondary"`, and either `stiction_lookback_days` is absent from `pool_state.json` or `event.day >= measurement.run_day - propagated_lookback`, where `propagated_lookback = stiction_lookback_days // 2` (integer floor division). Direct activation never crosses probes; chain propagation never fires for the event’s own probe even when that probe carries the `primary` role. Stiction events whose probe lacks the `primary` role (or lacks a chain pair) propagate to nothing. A measurement is **stiction-voided** when at least one accepted non-ignored `probe_stiction` event is either directly active or chain-propagated to it. A measurement is **chain-only stiction-voided** when it is stiction-voided AND no accepted non-ignored `probe_stiction` event is directly active for it (the void came exclusively through propagation).

## Recall lift, recall relift, and solvent recall activation

An accepted `recall_lift` is **applicable** to a measurement when the event is not ignored, `event.solvent_id` equals the measurement’s `solvent_id`, `event.day <= measurement.run_day`, and either `event.probe_id` is absent / the empty string (wildcard across probes) or `event.probe_id` equals the measurement’s `probe_id`.

An accepted `recall_relift` is **applicable** to a measurement under the same predicate as `recall_lift` (matching `solvent_id`, `event.day <= measurement.run_day`, and probe wildcard / equality). A relift event therefore points at the same solvent as the lift it overrules, but is independent of any specific lift event in the array.

For each measurement, compute the latest recall day `r_max_day` as the maximum `event.day` across accepted non-ignored `solvent_recall` events whose `solvent_id` equals the measurement’s `solvent_id` and whose `event.day <= measurement.run_day`. When no such recall exists, the recall is not active and the relift / lift comparison is skipped. When at least one such recall exists, compute the latest lift day `l_max_day` as the maximum `event.day` across **applicable** recall lifts for that measurement, and the latest relift day `rl_max_day` as the maximum `event.day` across **applicable** recall relifts for that measurement. Treat absent `l_max_day` or `rl_max_day` as strictly less than every integer day. The recall is **active** for the measurement iff `max(r_max_day, rl_max_day) >= l_max_day`; otherwise the recall is **lifted** and not active. Recalls and relifts each win ties against lifts on the same day (the comparison is `>=`, not `>`), and the latest day among recall and relift is the operation that drives the activation. When `rl_max_day` is defined, it is the relift’s latest applicable day regardless of whether the relift overrules anything.

## Effective temperature and viscosity flags

Let `T_base = measurement.temp_reported_K + pool_state.kelvin_offset_global`.

Let `T_visc = T_base + delta_drift` using the capped drift value above.

Let `T_eff = T_base + delta_drift + delta_bench` using the bench correction selection above. Bench corrections adjust the reported effective temperature and the Stokes diffusion estimate but do not shift the temperature used for viscosity bracketing.

Let `r_nm` be the measurement’s `hydrodynamic_radius_nm`. When `radius_floor_nm` is present in `pool_state.json`, replace `r_nm` with `max(r_nm, radius_floor_nm)`; when `radius_ceiling_nm` is present, replace `r_nm` with `min(r_nm, radius_ceiling_nm)` after the floor step. Missing bounds are skipped rather than substituted with sentinels. Increment `radius_clamped_count` once for each measurement row when this two-step clamp yields a value not bitwise identical in IEEE binary64 to the parsed `hydrodynamic_radius_nm` from the fragment.

To obtain `viscosity_cP`, load the solvent JSON whose `solvent_id` matches. Let the viscosity points be `[(T_i, η_i)]` sorted by `T_i` ascending. If `T_visc` is strictly less than `T_0`, use `η_0` and increment `viscosity_extrapolation_low_count` once for this measurement. If `T_visc` is strictly greater than the last `T_k`, use `η_k` and increment `viscosity_extrapolation_high_count` once. Otherwise find the unique index `j` with `T_j <= T_visc <= T_{j+1}`; when `T_visc` equals an interior knot shared by two segments, use the lower-index segment (the left interval). Interpolate linearly in temperature: `η = η_j + (η_{j+1}-η_j)*(T_visc-T_j)/(T_{j+1}-T_j)`.

Viscosity extrapolation counters increment only while processing a measurement whose final disposition is `ok` (the lookup still uses `T_visc` even though void rows never emit viscosity fields).

## Status precedence

If the measurement is stiction-voided (directly or via chain propagation), status is `probe_void`. Else if a solvent recall is **active** for the measurement (per the recall-lift / recall-relift rule above), status is `solvent_void`. Else status is `ok`.

When status is not `ok`, `d_stokes_nm2_per_s`, `temp_effective_K`, `viscosity_cP_used`, and `hydrodynamic_radius_nm_used` must be JSON `null`.

When status is `ok`, emit `temp_effective_K` as `T_eff` rounded to three fractional digits using the same half-even rule at `1e3` scale, emit `viscosity_cP_used` as `η` rounded to six fractional digits using half-even at `1e6` scale, emit `hydrodynamic_radius_nm_used` as the post-clamp `r_nm` rounded to six fractional digits using half-even at `1e6` scale, and emit the rounded diffusion value as specified above.

## Output: `diffusion_results.json`

Top-level key `entries`: array sorted ascending by `measurement_id`. Each object includes keys `measurement_id`, `probe_id`, `solvent_id`, `solute_id`, `temp_effective_K`, `viscosity_cP_used`, `hydrodynamic_radius_nm_used`, `d_stokes_nm2_per_s`, `status`.

## Output: `anomalies.json`

Top-level key `applied_events`: array of string `event_id` values sorted ascending. Include every accepted event that is not ignored by the reference rules and that satisfies at least one of:

- (a) it is a `sensor_drift` event that appears in the **drift contributors** set of at least one measurement whose final status is `ok` (a single drift event may be a contributor for several measurements; emit it once when any one of those measurements is `ok`);
- (a′) it is the selected `bench_correction` winner for at least one measurement whose final status is `ok`;
- (b) it is a `probe_stiction` that is directly active for at least one measurement OR chain-propagated to at least one measurement (either path counts; an event applied through both still appears once);
- (c) it is a `solvent_recall` and there exists at least one measurement for which it is the latest matching recall (its `event.day` equals `r_max_day` and ties resolve by later position in the `events` array) AND that recall is **active** for that measurement (i.e., not lifted, considering relifts per the rule above); the row’s final status need not actually be `solvent_void` (precedence by a stiction does not suppress emission);
- (d) it is a `recall_lift` and it is **applicable** to at least one measurement for which `r_max_day` is defined and `l_max_day >= r_max_day` (i.e., it would cancel an existing matching recall for that measurement on the lift-vs-recall axis alone, regardless of any later relift); ties resolve by later position in the `events` array when several lifts share `l_max_day`. Emit only those lifts whose `event.day` equals the measurement’s `l_max_day`;
- (e) it is a `recall_relift` and there exists at least one measurement for which it is **applicable**, `r_max_day` is defined, the recall is **active** for that measurement (per the joint rule above), and the event’s `day` equals the measurement’s `rl_max_day`. Ties resolve by later position in the `events` array when several relifts share `rl_max_day`. A relift that is applicable but encounters no matching recall (or whose measurement’s recall is not active) is not emitted.

Drift contributors (clause a) and the bench winner (clause a′) are evaluated after status precedence: contribution and selection still scan every measurement row, but an identifier is emitted only when at least one row that retains it is `ok`. Clauses (b), (c), (d), and (e) are precedence-blind: any matching measurement makes the identifier eligible regardless of `probe_stiction` or `solvent_recall` overlap.

## Output: `summary.json`

Top-level keys only: `measurements_total`, `ok_count`, `probe_void_count`, `solvent_void_count`, `ignored_incident_events`, `radius_clamped_count`, `drift_capped_count`, `viscosity_extrapolation_low_count`, `viscosity_extrapolation_high_count`, `chain_propagated_void_count`, `recall_relift_count`. All are non-negative integers computed across the measurement corpus after rules above.

`chain_propagated_void_count` is the number of measurements that are chain-only stiction-voided per the propagation rule (status `probe_void` with no directly active stiction event for the measurement’s own probe). `recall_relift_count` is the number of measurements for which `r_max_day` is defined, the recall is **active**, and `rl_max_day` is defined with `rl_max_day >= l_max_day` (i.e., a relift is the operation that drove the recall back to active). Both counters are zero when no chain propagation or relift activation occurs in the bundle.
