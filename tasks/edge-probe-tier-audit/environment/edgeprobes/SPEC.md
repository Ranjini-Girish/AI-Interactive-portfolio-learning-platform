# Edge probe tier audit

Inputs live beside this file. The audit reads `policy.json`, `pool_state.json`, `incidents.json`, every `*.json` file directly under `probes/`, every `*.json` file under `ancillary/`, and every `*.txt` file under `anchors/`. Paths under `ledger/` are packaging noise only.

## Canonical JSON

Emit every artifact as JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Policy

- `failed_status_floor` (integer): any probe whose `status_code` is greater than or equal to this value is `FAILED` before tier refinement.
- `rtt_fast_max_ms` and `rtt_moderate_max_ms` (integers): for probes that are not `FAILED`, classify by RTT using inclusive upper bounds: `rtt_ms <= rtt_fast_max_ms` is `FAST`, else if `rtt_ms <= rtt_moderate_max_ms` is `MODERATE`, else `SLOW`.
- `mad_k` (number): multiplier applied to each region's median absolute deviation when testing RTT outliers.

## Pool state

- `window_ms` (positive integer): divisor for throughput. Define `kbps = (bytes_down * 8) / window_ms` using integer division (floor toward zero for nonnegative values).

## Ancillary merges

Walk `ancillary/*.json` in ascending ASCII basename order. Each file may contribute:

- `region_min_kbps` (object mapping region name to integer floor). Later files overwrite earlier values for the same region key.
- `mad_exclude` (array of endpoint_id strings). Union every listed id into the exclusion set.

## Incident and anchor overrides

Collect notes from `incidents.json` (`notes` array objects with `endpoint_id` and `forced_tier`). Also parse each non-empty line in `anchors/*.txt` as two whitespace-separated tokens: `endpoint_id` then `forced_tier`. Sort the combined list by ascending `endpoint_id`; when the same id appears more than once, the later entry wins. Apply overrides only for ids that exist in the probe set; unknown ids are ignored. Overrides run after base SLO bucketing and before throughput demotion.

## Throughput demotion

After overrides, for every probe whose tier is not `FAILED`, if `kbps` is strictly less than `region_min_kbps[region]`, demote exactly one step: `FAST` becomes `MODERATE`, `MODERATE` becomes `SLOW`, and `SLOW` stays `SLOW`. Count probes whose tier changed in this step toward `throughput_demoted_total` in `summary.json`.

## Per-region MAD and anomalies

For each region independently, the MAD sample contains exactly those probes whose `status_code` is strictly less than `failed_status_floor` AND whose `endpoint_id` is not in the ancillary exclusion set. The MAD sample is the only set of probes ever eligible for `anomaly_flag = true`; every probe outside the sample (FAILED probes, excluded probes, and probes whose region has a sample size below the usable threshold) carries `anomaly_flag = false` unconditionally, regardless of its raw `rtt_ms` or any forced tier.

If a region's MAD sample size is fewer than three, that region's `global_median_ms` and `global_mad_ms` are JSON `null`, MAD is disabled for the region, and no probe in that region receives `anomaly_flag = true`.

Otherwise compute `global_median_ms` as the median of the sample's `rtt_ms` values (for an even count, use the average of the two central values with integer division rounding toward zero). Let deviations be `abs(rtt_ms - global_median_ms)` for each sample member; `global_mad_ms` is the median of those deviations using the same median rule. A probe in the MAD sample is flagged as an RTT outlier when either `rtt_ms > global_median_ms + mad_k*global_mad_ms` or `rtt_ms < global_median_ms - mad_k*global_mad_ms` (strict inequalities); such probes set `anomaly_flag` true. Non-outlier sample members keep `anomaly_flag` false. Outlier testing always uses raw `rtt_ms` regardless of forced tiers or throughput demotions.

## Outputs

Write five files to the audit directory:

1. `endpoint_profiles.json` with keys `endpoints` (array) then `window_ms` copied from pool state. Each endpoint object includes `anomaly_flag`, `endpoint_id`, `kbps`, `region`, `rtt_ms`, `status_code`, and `tier`. Sort `endpoints` by `endpoint_id` ascending.
2. `tier_rollups.json` with top-level keys `tiers` then `window_ms`. `tiers` maps region name to counts for `FAILED`, `FAST`, `MODERATE`, and `SLOW` using final tier labels after overrides and demotion. Regions sorted lexicographically; inside each region the tier keys are sorted lexicographically.
3. `anomaly_events.json` with `events`, a list sorted by `endpoint_id` ascending containing exactly one entry per probe whose `anomaly_flag` is true (and no entries for any other probe). Each event includes `deviation_ms` (`abs(rtt_ms - global_median_ms)` for that probe's region), `endpoint_id`, `global_mad_ms`, `global_median_ms`, and `rtt_ms` from the probe's regional MAD computation.
4. `mad_summary.json` with key `regions`, an array sorted by ascending `region`. Each element includes `global_mad_ms`, `global_median_ms`, `region`, and `sample_size` (integer count of that region's MAD sample members).
5. `summary.json` with keys `anomaly_total`, `endpoints_total`, `failed_total`, `regions`, `throughput_demoted_total`, and `window_ms`. `regions` lists distinct regions sorted lexicographically. `failed_total` counts probes with final tier `FAILED`. `anomaly_total` counts probes with `anomaly_flag` true. `throughput_demoted_total` counts probes demoted by the throughput step.

## Tooling

Read `EPT_DATA_DIR` defaulting to `/app/edgeprobes` and `EPT_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
