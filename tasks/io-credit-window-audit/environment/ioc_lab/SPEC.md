# IO credit window audit

Normative rules for `/app/ioc_lab` inputs and `/app/audit/report.json`.

## Inputs

Read `policy.json`, `devices.json`, `incidents.json`, and every `loads/*.json` sorted by full path ascending. Each load file is `{"device_id": string, "ticks": [{"t": int, "util": int}]}` where `util` is 0..100 inclusive. Merge ticks per `device_id`; when the same `t` appears in multiple files, the later sorted path overwrites earlier values.

`devices.json` is an array of `{"device_id": string, "queue_depth": int}` with non-negative `queue_depth`. Every `device_id` in `devices.json` appears in the report even if it has no samples.

## Policy fields

- `hot_util` int in 0..100.
- `median_k` positive odd integer. Half-width `h = median_k // 2`.
- `merge_gap_tol` non-negative int.
- `relief_delta` non-negative int.
- `depth_cap` float > 1.0.
- `depth_per_qd` float >= 0.

## Depth factor and threshold

For device `d`, `qd = queue_depth` from `devices.json`. `factor = min(depth_cap, 1.0 + qd * depth_per_qd)`. Integer threshold `thr(d) = ceil(hot_util * factor)`.

## Incident spans

`incidents.json` has `spans` array of `{"kind": string, "start_t": int, "end_t": int, "device_id"?: string}`. A span is active at tick `t` when `start_t <= t <= end_t`.

Kinds:

- `freeze` (no `device_id`): while active, no device may register a hot tick.
- `embargo` (requires `device_id`): while active for device `d`, `d` never registers a hot tick even if utilization would otherwise qualify.
- `credit_relief` (requires `device_id`): while active for `d`, compare smoothed utilization against `max(0, thr(d) - relief_delta)` instead of `thr(d)`.

When multiple spans overlap, apply all modifiers that affect the device and tick; `freeze` still blocks emission of hot ticks globally.

## Smoothed utilization

For device `d`, let `M` be its merged tick map. Let `t_min` and `t_max` be the minimum and maximum keys in `M`. For every integer `t` with `t_min <= t <= t_max`, collect every `M[t+dt]` that exists for integers `dt` in `[-h, h]`. If the collection is empty, skip `t`. Otherwise `smooth(d,t)` is the median of the collected integers using sorted order; for an even count, use the average of the two middle values with integer division toward zero for positives (sum of the two middle values divided by two using floor division for non-negative inputs).

## Hot predicate before freeze

`would_hot(d,t)` is true when no active `embargo` covers `(d,t)` and `smooth(d,t) >= effective_thr`, where `effective_thr` is `thr(d)` unless `credit_relief` is active for `(d,t)`, in which case it is `max(0, thr(d) - relief_delta)`.

## Final hot ticks

`hot(d,t)` is true iff `would_hot(d,t)` is true and no global `freeze` is active at `t`.

## Windows

For each device, list ticks `t` in `[t_min, t_max]` where `hot(d,t)` is true. Sort ascending. Merge into inclusive windows of consecutive integers. After that, repeatedly merge the earliest pair of windows `[a,b]` and `[c,d]` where `c <= b + 1 + merge_gap_tol`, replacing them with `[a, max(b,d)]`, until no merge applies. `hot_windows` is the final list sorted by start tick ascending; use an empty JSON array when there are no hot ticks.

## Verdicts

Let `L` be the maximum inclusive length among `hot_windows` entries (`end - start + 1`), or zero when empty.

- `cool` when there are no hot ticks.
- `warm` when there is at least one hot tick and `L < 3`.
- `hot` when `L >= 3`.

## Summary counts

- `devices_scanned`: length of `devices.json` array.
- `total_hot_ticks`: sum over devices of counts of ticks with `hot(d,t)` true within `[t_min, t_max]`.
- `total_windows`: sum of `len(hot_windows)` per device.
- `verdict_hot`, `verdict_warm`, `verdict_cool`: counts of devices by verdict.
- `freeze_suppressed_ticks`: count of pairs `(d,t)` with `t` in `[t_min, t_max]` for that device where a `freeze` is active at `t` and `would_hot(d,t)` is true.
- `relief_active_ticks`: count of pairs `(d,t)` with `t` in `[t_min, t_max]` for that device where `credit_relief` is active for `(d,t)`.

## Report encoding

Write `/app/audit/report.json` as UTF-8 JSON with two-space indentation, sorted object keys at every object level, ASCII-only text, no trailing spaces on lines, and a single trailing newline after the closing brace.

## Device ordering

The `devices` array must be sorted by `device_id` ascending using byte-wise UTF-8 lexicographic order.
