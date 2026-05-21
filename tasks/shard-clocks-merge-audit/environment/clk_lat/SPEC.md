# Shard clock merge

JSON must be UTF-8, sorted keys, two-space indent, ASCII-only, trailing newline.

## Inputs
`/app/clk_lat/policy.json` has integer `horizon_day`, string `baseline_id`, integer `penalty_ms`.
`/app/clk_lat/pool_state.json` has map `bonus_ms` keyed by segment id (ints, may be negative).
`/app/clk_lat/incidents.json` has `incidents` with `kind` among `falseticker`, `hold`, `lift_hold`.
Each `/app/clk_lat/segments/<id>.json` has string `id`, integer `skew_ms`, boolean `trusted_default`.

Only incidents with `accepted==true` and `day<=horizon_day` apply, ordered by `day` then `id`.

## Semantics
- `falseticker` marks the target segment untrusted for the remainder.
- `hold` marks the target frozen; frozen segments ignore pool bonuses and keep `bonus_skew` equal to `skew_ms`.
- `lift_hold` clears the frozen mark when accepted.
- Baseline skew is the integer `skew_ms` of the segment whose `id` equals `baseline_id`.

For each segment sorted by ascending `id`, `raw_skew` is `skew_ms`.
If frozen, `bonus_skew` equals `raw_skew`; otherwise add `bonus_ms[id]` defaulting to 0.
Trusted means `trusted_default` is true and the id is not falseticker-marked.
If trusted, `adjusted_skew = bonus_skew - baseline_skew`; else `adjusted_skew = bonus_skew + penalty_ms`.

## Outputs
`/app/audit/segments_out.json` with `rows` sorted by ascending `id`, fields `id`, integers `raw_skew`,
`bonus_skew`, `adjusted_skew`, booleans `trusted`, `frozen`.
`/app/audit/summary.json` with ints `trusted_count`, `untrusted_count`, `frozen_count`, `sum_adjusted`,
and string `baseline_id_out` equal to `baseline_id`.

Emit JSON with `json.dumps(..., sort_keys=True, indent=2, separators=(",", ": "))` plus trailing newline.
