# Slew rate cap audit (normative)

All JSON read and written by the audit must use UTF-8 without a byte order mark. The audit must write `/app/srl_audit/report.json` as pretty-printed JSON using two ASCII spaces per indent level, ASCII-only text, sorted object keys at every nesting depth, comma+space after each comma between values, colon+space after each colon, no trailing spaces on lines, and exactly one trailing newline after the closing brace. Logical content must match the normative rules below; whitespace may not smuggle extra keys.

## Inputs (read-only under `/app/srl_lab/`)

- `policy.json` object keys:
  - `slew_cap_milli` (int, >=0): breach when any adjacent segment slew exceeds this.
  - `merge_by_tag` (bool): when true, merge channels that share the same `tag` string before slew metrics; when false, each file is its own series.
  - `tie_break_dup_t` (string): either `min_v` or `max_v`. When merging series, if two points share the same integer `t`, the merged point uses the min or max of their `v` values accordingly.
- `pool_state.json` object keys:
  - `current_t` (int): only incident events with `apply_t <= current_t` are honored.
- `incident_log.json` object keys:
  - `events` (array): each event is an object with stable ordering processed as below.
- `channels/*.json` files: each file is one object with keys `channel_id` (string), `tag` (string), `points` (array of objects with integer `t` and integer `v`). Points may be unsorted in the file.
- Files under `anchors/` and `ancillary/` are human context only; the audit must not read them and must not mention them in output.

## Incident processing

Sort `events` ascending by `apply_t` then by `event_id` lexicographically. Walk in that order. Skip events with `apply_t > pool_state.current_t`. Supported `kind` values:

- `zero_window`: requires `channel_id`, `start_t`, `end_t` integers with `start_t <= end_t`. For the named channel only, any point whose `t` lies in the inclusive range becomes `v=0`. Other channels are untouched.
- `noop`: ignored except it still counts toward `summary.events_seen`.

Unknown kinds increment `summary.unknown_event_kinds` but otherwise leave state unchanged.

Zero windows apply to the **raw per-channel** series **before** any merge.

## Merge rule

When `merge_by_tag` is false, treat each `channel_id` independently. When true, partition channel files by exact `tag`. For each non-empty partition, build one merged series:

1. Collect all points from member channels.
2. Sort by `t` ascending; when `t` ties, sort by original `channel_id` ascending, then by original file path (POSIX string order of the basename under `channels/`) ascending.
3. Collapse equal `t` using `tie_break_dup_t`.

The merged series `id` is the string `join("+", sorted unique channel_ids in the partition)` using ASCII sort.

## Slew definition

Sort the final per-series points by `t` ascending (after merge collapse). If fewer than two points remain, `max_slew_milli` is 0 and `breach` is false. Otherwise for each adjacent pair `(t1,v1),(t2,v2)` with `t2>t1`, define `slew_milli = floor(abs(v2-v1) * 1000 / (t2-t1))`. The series `max_slew_milli` is the maximum of those values. `breach` is true iff `max_slew_milli > policy.slew_cap_milli`.

## Output `/app/srl_audit/report.json`

Top-level keys:

- `summary` object keys in sorted order:
  - `breach_count` (int): count of series entries with `breach==true`.
  - `channels_considered` (int): number of series rows in `channels` array.
  - `events_seen` (int): number of incident events examined after the sort (including skipped-by-time and unknown kinds).
  - `max_overall_milli` (int): maximum `max_slew_milli` across series (0 if none).
  - `unknown_event_kinds` (int): count of unknown `kind` values among honored-time events.
- `channels` array: one object per series after merge (or per raw channel when merge disabled), sorted by `id` ascending. Keys: `breach` (bool), `id` (string), `max_slew_milli` (int), `points` (int point count after preprocessing and merge collapse).

## Determinism

Channel files are discovered by glob `channels/*.json`; only basenames matching `^[a-z0-9][a-z0-9_-]*\\.json$` are read. Sort matching relative paths lexicographically before loading.
