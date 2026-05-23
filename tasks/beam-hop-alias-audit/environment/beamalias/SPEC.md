Normative contract for the beam hop alias audit. Inputs are UTF-8 JSON with ASCII-only strings. Outputs are UTF-8 JSON, ASCII-only, two-space indentation, recursively sorted object keys at every depth, no trailing spaces at line ends, and exactly one trailing newline after each root closing brace.

Read `policy.json` for integer `window_bins` (positive), float `nyquist_hz` (positive), integer `hop_span` (positive), and float `vote_ratio` between zero and one inclusive. Read `manifest.json` for `cal_tag` and `run_tag`. When they differ, multiply `nyquist_hz` by `0.5` for folding; round `effective_nyquist_hz` in summary to six decimals. Read `epochs.json` for integer `current_epoch`. Read `locks.json` for array `locks` with float `band_low`, `band_high`, and `lock_hz`. A frame frequency inside a closed band uses `lock_hz` as `report_freq_hz` and is not aliased. Read `frames.json` for array `frames` with integer `frame`, string `bin_id`, float `freq_hz`, and float `amplitude`.

Enumerate every `*.json` under `bins/`. Each bin has string `bin_id`, integer `epoch`, and float `weight`. A bin is stale when `epoch` is strictly less than `current_epoch - 1`. Active bins participate in band votes. Packaging under `anchors/`, `meta/`, and `grid/` is ignored.

Process frames in ascending `frame`, then ascending `bin_id`. When `frame` modulo `hop_span` is not zero and the bin carry buffer is positive, add that carry to amplitude as `hop_bonus` and count one hop carry in summary; after each frame where `frame` modulo `hop_span` equals zero, set the bin carry buffer to `0.5 * effective_amplitude` for the next hop cycle.

For frequency: if locked, `report_freq_hz` is the lock value and `aliased` is false. Else if `freq_hz` exceeds effective nyquist, `report_freq_hz` is `2 * effective_nyquist - freq_hz` rounded to six decimals and `aliased` is true. Else `report_freq_hz` is `freq_hz` rounded to six decimals and `aliased` is false.

Maintain per-bin FIFO of `report_freq_hz` capped at `window_bins`; `window_mean_freq` is the mean after append. Stale bins update windows but omit `alias_plan` rows.

Band bucket is `report_freq_hz` formatted with one decimal place. At a frame, `agree_weight` sums weights of active bins on the same frame whose bucket matches. Vote `accepted` when active and `agree_weight >= vote_ratio * total_active_weight`.

Emit `bin_states.json` with `bins` sorted by bin_id. Emit `alias_plan.json` with `entries` sorted by frame then bin_id for non-stale rows. Emit `band_votes.json` with `votes` in processing order. Emit `window_stats.json` with `windows` in processing order. Emit `summary.json` with alias_total, current_epoch, effective_nyquist_hz, frame_total, hop_carry_total, stale_skipped_total, vote_accepted_total.

Read `BHA_DATA_DIR` defaulting to `/app/beamalias` and `BHA_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
