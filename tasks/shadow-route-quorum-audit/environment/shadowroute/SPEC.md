# Shadow route quorum audit

Inputs live beside this file. Read `policy.json`, `pool_state.json`, `tiers.json`, `incidents.json`, every `*.json` under `routes/`, every `*.json` under `overlays/`, and every non-empty line in `pins/*.txt`. Paths under `registry/` are packaging metadata only.

## Canonical JSON

Emit every artifact as JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Policy

- `grace_days` (non-negative integer): a route is stale when `current_day - last_seen_day > grace_days`.
- `quorum_min` (positive integer): base quorum before tier weighting.
- `latency_median_k` (positive integer): sample count required before median latency is computed.
- `sample_floor` (non-negative integer): ignore shadow samples whose `latency_ms` is strictly less than this floor.

## Pool state

- `current_day`, `window_start_day`, `window_end_day` (integers): inclusive audit window on the day axis.

A **window sample** belongs to a route when `window_start_day <= day <= window_end_day`, `accepted` is true, and `latency_ms >= sample_floor`.

`last_seen_day` is the maximum `day` among all shadow samples on the route (including out-of-window samples). When a route has no samples, `last_seen_day` is JSON `null`.

## Tiers

`tiers.json` maps tier names to `shadow_fraction` (number in `[0, 1]`) and `quorum_weight` (positive number). Each route names a `tier` key that must exist in `tiers.json`.

`effective_quorum` is `max(1, ceil(quorum_min * quorum_weight))` using floating multiplication then rounding up to the nearest integer.

`shadow_fraction_effective` is the tier `shadow_fraction` unless the route status is `quarantined` (JSON `null`) or `blocked` (`0`).

## Overlay merge

Walk `overlays/*.json` in ascending ASCII basename order. Later files overwrite earlier values for the same key:

- `min_samples` (integer, default 1): minimum window-sample count for `sample_ok`
- `route_cap` (integer, default unlimited): unused in this audit revision (reserved)
- `exclude_models` (array of model_id strings): union every listed id

Routes whose `model_id` is excluded still appear in `route_profiles.json` with `sample_ok` false when window samples are insufficient or the model is excluded.

## Pins

Parse `pins/*.txt` lines as two whitespace-separated tokens: `model_id` then `forced_status`. Sort the combined list by ascending `model_id`; when the same id appears more than once, the later line wins. Allowed `forced_status` values: `hold`, `shadow_only`.

## Incidents

Parse `incidents.json` `events` with `kind`, `model_id`, `day`, and `accepted`.

- Accepted `model_compromise` quarantines the model and every route that uses it directly or transitively through `depends_on`.
- Accepted `route_freeze` forces `hold` on every route whose `model_id` matches when not quarantined.

## Dependency graph

Each route lists `depends_on` as model_id strings (may be empty). Build directed edges `(route_id, model_id)` for each dependency. A route is **dependency-blocked** when any dependency model is quarantined or carries pin `hold`, or when any upstream route that uses that model is quarantined (transitive closure over model ids referenced by `depends_on`).

`blocked` status overrides `degraded` and `stale` but not `quarantined`.

## Median latency and degraded

When a route has at least `latency_median_k` window samples, sort those samples by ascending `day` and take the last `latency_median_k` entries. The **median latency** is the middle value after sorting those latencies ascending (lower middle for even K). When fewer than `latency_median_k` window samples exist, `median_latency_ms` is JSON `null`.

Let the **latest window sample** be the window sample with the greatest `day` (tie-break by last array position in the route file). The route is **degraded** when `median_latency_ms` is not null, the latest window sample exists, and `latest.latency_ms > 2 * median_latency_ms`, and the route is not `quarantined` or `blocked`.

## Route status precedence

Apply the first matching rule:

1. `quarantined` when the route's `model_id` is compromised or transitively tied to a compromised model through `depends_on`.
2. `hold` when an accepted `route_freeze` targets the route's `model_id`, or pin `hold` applies to the route's `model_id`, and the route is not quarantined.
3. `blocked` when dependency-blocked and not quarantined.
4. `shadow_only` when pin `shadow_only` applies to the route's `model_id` and no higher rule matched.
5. `stale` when `last_seen_day` is not null and `current_day - last_seen_day > grace_days`.
6. `degraded` when the degraded rule fires.
7. `ok` otherwise.

## Route profile object

For each route file (basename without `.json` must equal `route_id`):

- `route_id`, `model_id`, `tier`, `last_seen_day`, `status`
- `effective_quorum`, `window_sample_count`, `sample_ok` (true when not excluded and count >= `min_samples`)
- `median_latency_ms` (integer or null), `shadow_fraction_effective` (number or null)

Sort the `routes` array by ascending `route_id`.

## Reports

`dependency_report.json` keys `edges` then `blocked_chains`. Each edge is `route_id`, `depends_on_model_id` sorted by `route_id` then `depends_on_model_id`. Each blocked chain row has `route_id`, `blocked_by_model_id`, `reason` (`compromised_upstream` or `hold_upstream`) sorted by `route_id`.

`degrade_report.json` lists routes with status `degraded` sorted by `route_id` with `route_id`, `model_id`, `median_latency_ms`, `latest_latency_ms`.

`compromise_report.json` keys `models` (distinct compromised model_id values, sorted) then `routes` (quarantined rows sorted by `route_id` with `route_id`, `model_id`).

## Summary

`summary.json` keys: `blocked_total`, `current_day`, `degraded_total`, `hold_total`, `quarantined_total`, `route_total`, `stale_total`, `window_end_day`, `window_start_day`.

## Outputs

Write five files to the audit directory:

1. `route_profiles.json` with keys `routes`, `window_end_day`, `window_start_day`.
2. `dependency_report.json` with keys `blocked_chains`, `edges`.
3. `degrade_report.json` with key `routes`.
4. `compromise_report.json` with keys `models`, `routes`.
5. `summary.json` as above.

## Tooling

Read `SRQ_DATA_DIR` defaulting to `/app/shadowroute` and `SRQ_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
