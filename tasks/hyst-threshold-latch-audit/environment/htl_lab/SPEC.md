# htl_lab bundle

## Canonical JSON
Emit UTF-8 JSON with `json.dumps(..., sort_keys=True, indent=2, separators=(', ', ': '))` plus trailing newline.

## policy.json
`high` > `low`. Hysteresis: start from `initial` in {`low`,`high`}.
Transition low->high when adjusted signal >= `high`.
Transition high->low when adjusted signal <= `low - latch_clear_margin`.
`latch_clear_margin` is a non-negative float subtracted from `low` on the falling threshold only.

## Points
Read `points/point_XX.json` sorted by filename with fields `t` int, `v` float, `mark` str. Process in ascending `t`.

## Incidents (applied before each point's evaluation in order of t)
- `bias_signal`: for integer times t with `t0 <= t <= t1`, add `add` to raw `v` before hysteresis.
- `force_low`: for times `t` with `t <= until`, after bias, if state would be high, coerce state to low without emitting a transition on that step unless the coerced state differs from previous emitted state (still emit if changed).
Apply incidents by scanning all incidents each step: first apply all applicable bias_signal adds, then apply force_low if any matches current t.

## Output latch_trace.json
`states` list objects `{t, v_raw, v_adj, state}` sorted by t ascending. `v_adj` after bias. `state` after rules.

## summary.json
Keys: `flips` int count of times state differs from previous emitted state between consecutive processed points, `high_steps` int count where final state is high, `points` int.
