Normative contract for the cap slice reclaim audit. Inputs are UTF-8 JSON with ASCII-only strings. Outputs are UTF-8 JSON, ASCII-only, two-space indentation, recursively sorted object keys at every depth, no trailing spaces at line ends, and exactly one trailing newline after each root closing brace.

Read `policy.json` for integer `window_size` (positive), float `soft_cap` (positive), integer `warmup_steps`, and float `tier_ratio` between zero and one inclusive. Read `manifest.json` for `monitor_tag` and `run_tag`. When they differ, multiply `soft_cap` by `0.5` and use the halved value for all reclaim math; round `effective_soft_cap` in summary to six decimals. Read `epochs.json` for integer `current_epoch`. Read `events.json` for array `events` with integer `step`, string `slice_id`, float `bytes_used`, and string `tier` in `high`, `med`, or `low`.

Enumerate every `*.json` under `slices/`. Each slice has string `slice_id`, integer `epoch`, and float `weight`. A slice is stale when `epoch` is strictly less than `current_epoch - 1`. Active slices participate in tier weight sums. Packaging under `anchors/`, `meta/`, and `grid/` is ignored.

Process events in ascending `step`, then ascending `slice_id`. Maintain per-slice FIFO history of `bytes_used` capped at `window_size`. `window_mean_bytes` is the arithmetic mean after appending the current sample.

For each event, when `step` is less than or equal to `warmup_steps`, `reclaim_factor` is `0.0` and `reclaimed` is false. Otherwise when `window_mean_bytes` exceeds the effective soft cap and `bytes_used` is positive, `reclaim_factor` is `min(1.0, (window_mean_bytes - effective_soft_cap) / bytes_used)`; `reclaimed` is true when `reclaim_factor` is strictly greater than zero. Otherwise both are zero and false. Stale slices still update window history but omit `reclaim_plan` rows.

Tier vote at a step: `agree_weight` sums `weight` of active slices whose event on the same `step` shares the same `tier`. The vote is `accepted` when the slice is active and `agree_weight >= tier_ratio * total_active_weight`, where `total_active_weight` sums active slice weights once.

Emit `slice_states.json` with `slices` sorted by `slice_id` (epoch, slice_id, stale, weight). Emit `reclaim_plan.json` with `entries` sorted by step then slice_id for non-stale rows only (bytes_used, reclaim_factor, reclaimed, slice_id, step). Emit `tier_votes.json` with `votes` in processing order (accepted, agree_weight, slice_id, step, stale, tier). Emit `window_stats.json` with `windows` in processing order. Emit `summary.json` with current_epoch, effective_soft_cap, reclaimed_total, stale_skipped_total, step_total, tier_accepted_total.

Read `CSR_DATA_DIR` defaulting to `/app/capslice` and `CSR_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
