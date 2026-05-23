Normative contract for the SLO burn-rate window audit. Inputs are UTF-8 JSON with ASCII-only strings. Outputs use two-space indentation, recursively sorted object keys, ASCII only, and exactly one trailing newline per root object.

Read `policy.json` for integer `window_slots` (W >= 1), integer `warmup_slots` (U >= 0), integers `burn_num` and `burn_den` (threshold is `burn_num / burn_den`), array `critical_hosts` of host id strings, and string `fleet_tag`. Read `view.json` for strings `ops_tag` and integer `freeze_epoch` (witness only). When `ops_tag` differs from `fleet_tag`, increase the effective warmup by one before filtering samples.

Read `incidents.json` for string `active_freeze_tag`. Read `blackout.json` for array `windows`; each window has string `host_id` (a concrete host id or `*` for all hosts), integer `start_slot`, and integer `end_slot` inclusive. A sample at slot `s` on host `H` is blacked out when some window matches `host_id` in `{H, *}` and `start_slot <= s <= end_slot`. For blacked-out samples, count `ok` toward denominators but treat `err` as zero when accumulating burn numerators.

Enumerate every `*.json` under `hosts/`. Each host object has string `host_id`, string `freeze_tag`, and array `samples` sorted by ascending `slot`. Each sample has integer `slot`, integer `ok` (>= 0), and integer `err` (>= 0). Files under `anchors/`, `ancillary/`, `grid/`, and `meta/` are packaging stubs only.

After applying the effective warmup filter, consider only samples with `slot >= effective_warmup`. The active window for a host is the last W such samples by slot order (fewer when not enough remain). Let `num` be the sum of effective error counts and `den` the sum of `ok + effective_err` across the active window. `burn_ppm` is `floor(1_000_000 * num / den)` when `den > 0`, else `0`. The host breaches when `den > 0` and `num * burn_den >= burn_num * den`.

Status precedence: when `host_id` is listed in `critical_hosts` and the host breaches, status is `breach` even if `freeze_tag` differs from `active_freeze_tag`. Otherwise, when `freeze_tag` differs from `active_freeze_tag`, status is `frozen`. Otherwise, when the host breaches, status is `breach`. Otherwise `active`.

Emit `host_states.json` with `effective_warmup` copied from the computed warmup and `hosts` sorted by `host_id`. Each row includes `burn_ppm`, `den`, `host_id`, `last_slot` (max slot in the active window, or `-1` when empty), `num`, and `status`.

Emit `window_burns.json` with `burn_windows` sorted by `host_id`. Each row repeats `burn_ppm`, `den`, `host_id`, `num`, and `sample_count` (window size).

Emit `fleet_summary.json` with integers `active_total`, `blackout_zeroed_errors`, `breach_total`, `effective_warmup`, `fleet_burn_ppm`, `fleet_den`, `fleet_num`, `frozen_total`, and `host_total`. Fleet numerators and denominators sum `num` and `den` only from hosts whose status is `active` or `breach`. `fleet_burn_ppm` uses those totals. `blackout_zeroed_errors` counts how many sample errors were zeroed by blackout across all hosts.

Environment variables `SBW_DATA_DIR` default `/app/sloburn` and `SBW_AUDIT_DIR` default `/app/audit`. Create the audit directory when missing and never mutate inputs.
