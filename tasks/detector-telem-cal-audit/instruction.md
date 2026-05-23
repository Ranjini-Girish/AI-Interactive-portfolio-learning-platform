# Detector Telemetry Calibration & Drift

You're given an eight-channel detector dataset under `/app/detector/` with twenty-two acquisition runs. Read every input file there and write a single JSON report to `/app/detector/report.json`. Don't touch any other file under `/app/detector/`.

A C++17 starter at `/app/environment/calibrate.cpp` builds via `make -C /app/environment build`; Python 3 is also installed. Either is fine.

The inputs:

- `policy.json` — thresholds and tunables: `min_calibration_points`, `outlier_k_sigma`, `outlier_max_iterations`, `residual_warning_threshold`, `signal_match_tolerance`, `signal_deviation_warning_threshold`, `drift_max_deviation_threshold`, `drift_stddev_threshold`, `event_anomaly_z_threshold`, `anomaly_min_events`, `anomaly_burst_threshold`, `min_correlation_runs`, `cross_channel_corr_threshold`, `min_run_health`, and a `severity_ranks` map (`critical`, `high`, `medium`, `low`, `info`).
- `channels.json` — the eight channels.
- `calibration.json` — reference triples `(raw, true, weight)` per channel; every reference carries a non-negative `weight`.
- `expected_signals.json` — target signals classified per `(run_id, channel_id)`.
- `manifest.json` — the run list.
- `exclusions.json` — channels, runs, and signals to drop.
- `runs/run_NNN.tsv` — tab-separated `event_id`, `channel_id`, `raw_value`.

**Calibration.** For each non-excluded channel with at least `min_calibration_points` reference points, fit `true ≈ slope · raw + offset` by *weighted* least squares using each reference's `weight`. With `S = Σ wᵢ`, the weighted means are `x̄ = (Σ wᵢ·xᵢ)/S` and `ȳ = (Σ wᵢ·yᵢ)/S`; `slope = (Σ wᵢ·(xᵢ−x̄)·(yᵢ−ȳ)) / (Σ wᵢ·(xᵢ−x̄)²)` and `offset = ȳ − slope·x̄`. The reported `residual_stddev` is the *weighted population* residual standard deviation, `√( (Σ wᵢ·rᵢ²) / S )` with `rᵢ = yᵢ − (slope·xᵢ + offset)` — note the denominator is `S`, not the count. After each fit, drop every kept reference whose `|rᵢ|` exceeds `outlier_k_sigma · residual_stddev`, recompute `S` and the means on what remains, and refit. `iterations_used` counts every fit that was performed; the initial fit is iteration 1, so a channel that converges with no rejections reports `iterations_used = 1`. Stop when no point is dropped in an iteration, when fewer than two points would remain, or after `outlier_max_iterations` iterations. Each `per_channel_calibration` row has `channel_id`, `n_reference_points` (the count of reference triples in `calibration.references[channel_id]`, regardless of status), `slope`, `offset`, `residual_stddev`, `n_outliers_removed`, `iterations_used`, and `status` (`calibrated` for a successful fit). Excluded channels and channels with too few references get identity calibration (`slope=1.0`, `offset=0.0`, the rest zero) and `status` of `excluded` or `insufficient_points`. When a fit's `residual_stddev` is exactly zero, no point is dropped.

**Per-run summary.** For every active run, calibrate every event as `calibrated = slope · raw + offset` and drop events on excluded channels. Each `per_run_summary` row has `run_id`, `status` (`active` or `excluded`), `n_events_total`, `event_counts_per_channel` (a `channel_id → count` map), `mean_calibrated_per_channel` (a `channel_id → mean calibrated value` map), `n_anomalous_events_per_channel`, `total_anomalous_events`, and `health_score`. Within each `(run, channel)` with at least `anomaly_min_events` events, an event is anomalous when `|calibrated − within-run-mean| > event_anomaly_z_threshold · within-run-stddev` (population stddev — denominator equal to the event count; if exactly zero, nothing is anomalous). `n_anomalous_events_per_channel` only contains channels with at least one anomaly, `total_anomalous_events` is their integer sum, and `health_score = 1 − total_anomalous_events / n_events_total` (or `1.0` when the run has no events). Excluded runs report `status="excluded"`, `n_events_total=0`, empty per-channel maps, `total_anomalous_events=0`, and `health_score=null`.

**Signal assignments.** For every signal in `expected_signals.json`, emit a row with `signal_id`, `run_id`, `channel_id`, `expected_value`, `status`, `n_matches`, `mean_calibrated_value`, and `deviation`. A signal is `excluded` when it (or its run) is excluded or its channel is excluded or not calibrated. Otherwise it is `matched` when at least one event on the named `(run, channel)` calibrates within `signal_match_tolerance` of `expected_value` — record the count of those events, their mean, and `mean − expected_value` — and `missing` when none qualifies. For `excluded` and `missing`, set `n_matches=0` and use `null` for the mean and the deviation.

**Drift and correlation.** For each calibrated channel, summarise its per-active-run calibrated means: `n_runs_with_events`, `mean_across_runs`, population `stddev_across_runs`, `max_run_deviation` (the largest absolute `per_run_mean − mean_across_runs`), and `drift_status` (`drifting` when either threshold in policy is exceeded, otherwise `stable`). Insufficient-points channels are kept out of drift, correlation, and non-excluded signal assignments. For every unordered pair of calibrated channels co-occurring (both producing at least one event) in at least `min_correlation_runs` active runs, emit `{channel_a, channel_b, n_runs, pearson_r}` over their per-run calibrated means; if either variance is zero, `pearson_r=0.0`.

**Quality findings.** Emit findings whenever these conditions hold, using the listed `finding_type`, `severity`, and `subject`:

- non-excluded channel with too few references → `insufficient_calibration_points`, severity `high`, subject `channel`, evidence `n_reference_points`, `min_required`.
- calibrated channel whose `residual_stddev` exceeds `residual_warning_threshold` → `large_calibration_residual`, severity `high`, subject `channel`, evidence `residual_stddev`, `threshold`, `slope`, `offset`.
- calibrated channel that lost any reference points to outlier rejection → `outliers_rejected_in_calibration`, severity `info`, subject `channel`, evidence `n_outliers_removed`, `k_sigma`, `iterations_used`.
- non-excluded signal with no qualifying events → `signal_missing`, severity `medium`, subject `signal`, evidence `expected_value`, `tolerance`, `n_matches`.
- matched signal whose `|deviation|` exceeds `signal_deviation_warning_threshold` → `signal_value_mismatch`, severity `high`, subject `signal`, evidence `expected_value`, `mean_calibrated_value`, `deviation`, `threshold`, `n_matches`.
- calibrated channel whose drift status is `drifting` → `channel_drifting`, severity `critical`, subject `channel`, evidence `max_run_deviation`, `stddev_across_runs`, `max_deviation_threshold`, `stddev_threshold`, `n_runs_with_events`.
- `(run, channel)` pair whose anomalous-event count reaches `anomaly_burst_threshold` → `anomalous_event_burst`, severity `high`, subject `run` (the burst is attributed to the run), evidence `n_anomalous`, `n_events_in_channel`, `z_threshold`, `burst_threshold`.
- active run whose `health_score` is below `min_run_health` → `low_run_health`, severity `high`, subject `run`, evidence `health_score`, `threshold`, `n_anomalous_events`, `n_events_total`.
- correlation row whose `|pearson_r|` exceeds `cross_channel_corr_threshold` → `unexpected_channel_correlation`, severity `medium`, subject `channel`, evidence `channel_a`, `channel_b`, `pearson_r`, `threshold`, `n_runs`; the finding's `channel_id` is the row's `channel_a`.
- one finding per excluded channel, run, and signal — `excluded_channel` (subject `channel`), `excluded_run` (subject `run`), `excluded_signal` (subject `signal`), all `info`, each with an empty `evidence` object. `excluded_signal` carries the originating signal's `channel_id`, `run_id`, and `signal_id`.

Every finding has these keys: `finding_type`, `severity`, `severity_rank` (looked up in `policy.severity_ranks`), `subject` (per the table above), `channel_id`, `run_id`, `signal_id` (use `null` for any that does not apply, except as noted above), and `evidence`.

**Output.** One JSON object at `/app/detector/report.json`, two-space indent, trailing newline, with these top-level keys exactly:

```json
{
  "schema_version": 1,
  "summary": { ... },
  "per_channel_calibration": [ ... ],
  "per_run_summary": [ ... ],
  "signal_assignments": [ ... ],
  "channel_drift_summary": [ ... ],
  "channel_correlation_matrix": [ ... ],
  "quality_findings": [ ... ]
}
```

`summary` carries `total_channels`, `calibrated_channels`, `total_runs`, `active_runs`, `excluded_runs`, `total_events_processed`, `total_anomalous_events`, the six `*_count` fields equal to the lengths of the corresponding lists, `by_severity` (always all five severity keys, zeros for absent ones), and `by_finding_type` (only types that occurred).

Sort `per_channel_calibration`, `per_run_summary`, and `channel_drift_summary` by their identifier; sort `signal_assignments` by `(signal_id, run_id)`; sort `channel_correlation_matrix` by `(channel_a, channel_b)`; sort `quality_findings` by `severity_rank` descending, then `finding_type`, `channel_id`, `run_id`, `signal_id` ascending (treat `null` identifiers as the empty string). Round every floating-point field in the report to six decimal places; integers stay integers and `null` stays `null`.
