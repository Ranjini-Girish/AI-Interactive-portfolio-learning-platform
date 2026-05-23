# Hysteresis bridge audit (normative)

This file is the single source of truth for parsing, ordering, rounding, and output shape. All paths are relative to the lab root directory named in `instruction.md` (the directory that contains this `SPEC.md`).

## Canonical JSON

Every output file is UTF-8 JSON with sorted object keys, two-space indentation, comma+space separators, ASCII-only text, and exactly one trailing newline after the closing brace. Numbers are emitted as JSON numbers (no string wrapping). Serialize nested fragments with the same rules before hashing.

## Required inputs

The lab ships `policy.json`, `pool_state.json`, `incident_log.json`, `domain_layout.json`, `anchors/window.json`, `anchors/cap.json`, `ancillary/meta.json`, `ancillary/scale.json`, `ancillary/notes.json`, every `lanes/l*.json`, and every `ticks/tick_*.json`. The anchors and ancillary files marked as witnesses must parse as JSON but only `anchors/window.json`, `ancillary/scale.json`, and the lane and tick bodies influence the audit math.

## Adjustment rule

For each tick row, let `raw` be its numeric `value`, `bias` be `pool_state.json.bias`, and `scale` be `ancillary/scale.json.scale`. The adjusted sample is `round3((raw + bias) * scale)` where `round3` keeps three fractional decimal digits using the round-half-even tie-breaking of Python’s `format(x, ".3f")` followed by `float(...)`.

## Window gate

Let `start_day` and `end_day` be inclusive integers from `anchors/window.json`. A tick whose integer `day` is strictly less than `start_day` or strictly greater than `end_day` is ignored for evaluation and does not reset or advance debounce streaks.

## Incident blind

`incident_log.json` contains an `events` array. An event with `kind` equal to the literal `day_blind`, `accepted` equal to true, inclusive `from_day`/`to_day` range, and a `lanes` array is active on integer day `d` for lane id `L` when `d` is between `from_day` and `to_day` inclusive and either `lanes` contains the string `*` or `lanes` contains `L`. When active, the matching tick for that lane on that day is skipped: it does not increment `ticks_evaluated`, does not compare thresholds, and forces both debounce streak counters for that lane back to zero without emitting a crossing.

## Lane definitions

Each `lanes/l*.json` object must include string `lane_id`, numbers `low_thresh` and `high_thresh`, and string `start_state` which is exactly `low` or `high`. Files are discovered only through the glob `lanes/l*.json` sorted by full path. Lane parameters are not merged across files; duplicate `lane_id` values are forbidden by the fixture set.

## Tick ordering

Read every `ticks/tick_*.json` file, then sort the combined records by ascending integer `day`, then ascending ASCII `lane_id`, then ascending tick file path as a final tie-break. Each file contains one object with integer `day`, string `lane_id`, and numeric `value`. Ticks whose `lane_id` is absent from the lane map are ignored entirely: they do not affect streaks or counters.

## Debounced hysteresis

Let `K` be the positive integer `policy.json.debounce_required`. Each lane maintains `state` starting at `start_state`, plus two integer streak counters `toward_high` and `toward_low`, both initially zero.

When a tick is evaluated (passes window, not blind, known lane):

- If `state` is `low`, set `toward_low` to zero. If `adjusted >= high_thresh`, increment `toward_high` by one; otherwise set `toward_high` to zero. If after this increment `toward_high >= K`, emit one crossing, flip `state` to `high`, then set both streak counters to zero.
- If `state` is `high`, set `toward_high` to zero. If `adjusted <= low_thresh`, increment `toward_low` by one; otherwise set `toward_low` to zero. If after this increment `toward_low >= K`, emit one crossing, flip `state` to `low`, then set both streak counters to zero.

Each crossing record is an object with keys `day`, `lane_id`, `from_state`, `to_state`, and `streak_at_flip` (the integer `K`). After any flip, do not evaluate additional rules on the same tick.

## Outputs

Write exactly two files into the audit directory: `summary.json` and `crossing_log.json`.

`summary.json` must contain keys `ticks_seen`, `ticks_evaluated`, `crossing_events`, `debounce_required`, `start_day`, `end_day`, `lanes`, and `incidents_applied`. `ticks_seen` is the count of all tick files after the initial sorted-by-path glob regardless of whether they were evaluated. `ticks_evaluated` counts ticks that were evaluated under the window and blind rules. `crossing_events` is the length of the crossing list. `lanes` is the list of lane ids sorted ASCII ascending. `incidents_applied` counts events in `incident_log.json` whose `accepted` field is true (any kind).

`crossing_log.json` must contain keys `crossings` (array of crossing objects ordered by ascending `day` then ascending `lane_id`) and `final_state` (object mapping each lane id sorted ASCII ascending to its final `low` or `high` string).

## Witness discipline

`domain_layout.json`, `anchors/cap.json`, `ancillary/meta.json`, and `ancillary/notes.json` are witness files. They must remain byte-identical to the shipped copies for integrity checks; readers may parse them but must not require mutating them.
