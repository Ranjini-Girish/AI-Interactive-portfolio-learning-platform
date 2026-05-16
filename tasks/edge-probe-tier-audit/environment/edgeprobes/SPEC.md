# Edge probe tier audit

Inputs live beside this file. The audit reads `policy.json`, `pool_state.json`, `incidents.json`, and every `*.json` file directly under `probes/`. Paths under `ledger/`, `ancillary/`, and `anchors/` are packaging noise only.

## Canonical JSON

Emit every artifact as JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Policy

- `failed_status_floor` (integer): any probe whose `status_code` is greater than or equal to this value is `FAILED` before tier refinement.
- `rtt_fast_max_ms` and `rtt_moderate_max_ms` (integers): for probes that are not `FAILED`, classify by RTT using inclusive upper bounds: `rtt_ms <= rtt_fast_max_ms` is `FAST`, else if `rtt_ms <= rtt_moderate_max_ms` is `MODERATE`, else `SLOW`.
- `mad_k` (number): multiplier applied to the global median absolute deviation when testing RTT outliers.

## Pool state

- `window_ms` (positive integer): divisor for throughput. Define `kbps = (bytes_down * 8) / window_ms` using integer division (floor toward zero for nonnegative values).

## Incidents

`notes` is an array of objects sorted by ascending `endpoint_id` before matching. When a note references an existing probe `endpoint_id`, replace that probe's computed tier string with `forced_tier` from the note. Notes that reference unknown endpoints are ignored. Anomaly detection still uses raw measurements regardless of forced tiers.

## MAD and anomalies

Collect every probe with `status_code` strictly less than `failed_status_floor` into the global MAD sample using its `rtt_ms`. If the sample size is fewer than three, set both `global_median_ms` and `global_mad_ms` to JSON `null` in `mad_summary.json`, emit no anomaly events, and set `anomaly_flag` false for every probe.

Otherwise compute `global_median_ms` as the median of the multiset (for an even count, use the average of the two central values with integer division rounding toward zero). Let deviations be `abs(rtt_ms - global_median_ms)` for each sample; `global_mad_ms` is the median of those deviations using the same median rule. A probe is an RTT outlier when it is part of the MAD sample and either `rtt_ms > global_median_ms + mad_k*global_mad_ms` or `rtt_ms < global_median_ms - mad_k*global_mad_ms` (strict inequalities). Outliers set `anomaly_flag` true; all other probes have `anomaly_flag` false.

## Outputs

Write five files to the audit directory:

1. `endpoint_profiles.json` with keys `endpoints` (array) then `window_ms` copied from pool state. Each endpoint object includes `anomaly_flag`, `endpoint_id`, `kbps`, `region`, `rtt_ms`, `status_code`, and `tier`. Sort `endpoints` by `endpoint_id` ascending.
2. `tier_rollups.json` with top-level keys `tiers` then `window_ms`. `tiers` maps region name to counts for `FAILED`, `FAST`, `MODERATE`, and `SLOW` using the final tier labels after incident overrides. Regions sorted lexicographically; inside each region the tier keys are sorted lexicographically.
3. `anomaly_events.json` with `events`, a list sorted by `endpoint_id` ascending. Each event includes `deviation_ms` (`abs(rtt_ms - global_median_ms)`), `endpoint_id`, `global_mad_ms`, `global_median_ms`, and `rtt_ms`. When MAD is disabled, `events` is an empty array.
4. `mad_summary.json` with keys `global_mad_ms`, `global_median_ms`, `sample_size` (integer count of MAD sample members).
5. `summary.json` with keys `endpoints_total`, `failed_total`, `regions`, and `window_ms`. `regions` lists distinct regions sorted lexicographically. `failed_total` counts probes with final tier `FAILED`.

## Tooling

Read `EPT_DATA_DIR` defaulting to `/app/edgeprobes` and `EPT_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
