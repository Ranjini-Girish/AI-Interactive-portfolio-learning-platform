# Fair queue token laboratory — normative specification

## Scope
Relative paths below are rooted at `/app/fqt_lab/`. The audit writes exactly two UTF-8 JSON files under `/app/audit/`: `serve_trace.json` and `summary.json`.

## Inputs
- `policy.json` contains `active_queues` (array of queue names), `queues` (map of queue name to `{ "w": <int> }` where `w` is a positive integer weight), integer `slice_max` (>0), and integer `max_cycles` (>0).
- `pool_state.json` contains integer `token_budget` (non-negative).
- `incident_log.json` contains ordered `events`.
- `anchors/window.json` contains integer `high_mark` (default `0` if missing or not an int).
- `ancillary/meta.json` contains optional string `label` echoed into summary.
- `jobs/job_XX.json` for `XX` from `00` to `17` inclusive — each object `{ "id": <str>, "queue": <str>, "demand": <int>, "stamp": <int> }`.

## Incident replay (before simulation)
Process `events` in file order; `applied_events` counts each object.
- `boost_weight` — fields `queue` (string) and `add` (integer, may be negative). Increase that queue’s `w` by `add`, clamping at `1` minimum.
- `freeze_queue` — field `queue` (string). Remove every job whose `queue` equals that value from the working set permanently.

Only jobs whose `queue` is listed in `active_queues` participate initially; jobs on unknown queues are ignored for the entire audit.

## Scheduler
Maintain integer `deficit[q]` for every `q` in `active_queues`, initially `0`. Maintain integer `tokens` copied from `pool_state.token_budget`.

For `cycle` running from `1` through `policy.max_cycles` inclusive:
1. For each `q` in `active_queues` sorted ascending by name, add the current integer weight `w[q]` to `deficit[q]`.
2. Let `candidates` be queues in `active_queues` that currently host at least one job with remaining demand `> 0` after freezes.
3. If `candidates` is empty or `tokens == 0`, stop the outer loop immediately after recording nothing further for this cycle.
4. Let `focus` be the subset of `candidates` whose `deficit[q]` is maximal. Choose `q*` as the lexicographically smallest queue name inside `focus`.
5. Among jobs assigned to `q*` with remaining demand `> 0`, pick the job minimizing `(stamp ascending, id ascending)`.
6. Let `serve = min(slice_max, job_remaining, tokens)`. If `serve == 0`, stop the outer loop.
7. Append one slice record `{ "cycle": cycle, "job_id": <id>, "queue": q*, "served": serve }` to the trace list in emission order (the list grows over time).
8. Decrease that job’s remaining demand by `serve`, decrease `tokens` by `serve`, and decrease `deficit[q*]` by `serve`.

Weights changed by incidents are used for all subsequent cycles.

## Outputs
### serve_trace.json
```json
{ "slices": [ { "cycle": 1, "job_id": "...", "queue": "Q0", "served": 3 }, ... ] }
```

### summary.json
```json
{
  "applied_events": <int>,
  "label": "<string>",
  "score": <int>,
  "slices_emitted": <int>,
  "token_remaining": <int>
}
```
`slices_emitted` is the length of the `slices` array. `token_remaining` is the final `tokens` value. `label` comes from `ancillary/meta.json["label"]` when it is a string, else empty string. Let `H` be the integer `anchors/window.json["high_mark"]` when valid, else `0`. Define `score = max(0, slices_emitted - H)`.

## On-disk JSON encoding
Use `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` with a trailing newline.
