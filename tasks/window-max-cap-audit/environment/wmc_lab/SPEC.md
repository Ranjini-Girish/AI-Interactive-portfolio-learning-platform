# Window maximum with cap audit

Normative UTF-8 JSON without a byte order mark. Canonical emitted JSON uses
two-space indentation, recursively sorted object keys, ASCII-only text, no
trailing spaces on lines, and exactly one trailing newline at EOF.

## Inputs

Data root defaults to `/app/wmc_lab/`.

- `domain_layout.json` lists `parts`, an ordered array of part identifiers.
  Each identifier must have a matching `parts/<id>.json` file with keys
  `part_id` and `values` (integer array, possibly empty).
- `policy.json` supplies integer `window` (>=1; values below one are treated as
  one) and integer `cap` (initial maximum applied after each window maximum).
- `pool_state.json` supplies inclusive `current_day`.
- `anchors/day_floor.json` supplies inclusive lower day `start_day` for
  incidents. `anchors/window.json` is informational only.
- `incident_log.json` supplies `events` processed in ascending `(day,
  event_id)` order.

## Incident eligibility

An event is **eligible** when it has `event_id`, numeric `day`, non-empty
`kind`, and `start_day <= day <= current_day`. Otherwise it is **ignored**
(counted only). Unknown kinds are ignored.

Supported kinds:

- `bump_cap` with numeric `new_cap` (>=0). Replaces the working cap with the
  larger of the current cap and `new_cap` rounded toward zero.
- `zero_index` with numeric `index` pointing at a position in the fully
  concatenated sample vector (after parts are joined in layout order, zero
  based). Sets that sample entry to zero when the index is in range.

Eligible events append to `applied` with recursively sorted object keys.

## Sliding window

Concatenate every part’s `values` in `domain_layout.parts` order to form the
working vector. After incidents, if the vector length is shorter than the
window width, emit empty outputs as specified below. Otherwise for each start
index `s` from `0` through `len(values)-window` inclusive, compute `raw_max` as
the maximum of the contiguous slice `values[s : s+window]`. The reported value
is `min(raw_max, cap)` using the cap after incidents.

## Outputs

Write four UTF-8 JSON files to the audit root (default `/app/wmc_audit/`):

1. `dilated_series.json` with object key `values`, the capped outputs in
   ascending start order.
2. `window_trace.json` with object key `windows`, an array of objects with keys
   `capped`, `raw_max`, and `start` sorted by ascending `start`.
3. `incident_trail.json` with `applied` (processing order) and `ignored`
   (integer count).
4. `summary.json` with integer fields: `applied_incidents`, `cap_final`,
   `current_day_used`, `ignored_incidents`, `incident_day_floor_used`,
   `output_len`, `total_input_len`, `window_used`.
