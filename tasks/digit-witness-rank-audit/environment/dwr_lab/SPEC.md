# Digit witness rank audit

Normative UTF-8 JSON without a byte order mark. Canonical emitted JSON uses
two-space indentation, recursively sorted object keys, ASCII-only text, no
trailing spaces on lines, and exactly one trailing newline at EOF.

## Inputs

Data root defaults to `/app/dwr_lab/`.

- `domain_layout.json` lists `lanes`, an array of lane identifiers. Each must
  have a matching `lanes/<lane_id>.json` file with keys `lane_id` and
  `readings` (array of integers; empty arrays are allowed).
- `policy.json` supplies `radix_base` (integer >= 2; values below 2 are
  treated as 2) and `witness_k` (non-negative integer count of rows kept per
  lane after ranking; counts beyond the available readings keep all rows).
- `pool_state.json` supplies inclusive `current_day`.
- `anchors/day_floor.json` supplies inclusive lower day `start_day` for
  incidents. `anchors/window.json` is informational only.
- `incident_log.json` contains `events` processed in ascending `(day,
  event_id)` order.

## Incident eligibility

An event is **eligible** when it has `event_id`, numeric `day`, non-empty
`kind`, and `start_day <= day <= current_day`. Otherwise it is **ignored**
(counted only). Unknown kinds are ignored.

Supported kinds:

- `bump_radix` with numeric `new_base` (>=2). Sets the working radix to the
  larger of the current radix and `new_base` rounded toward zero.
- `suppress_lane` with string `lane_id` present in `domain_layout.lanes`.
  Suppressed lanes are omitted entirely from witness construction.

Eligible events are appended to `applied` using their original fields but
with object keys sorted recursively at every nesting level.

## Witness construction

After incidents, for every lane not suppressed, rank its readings using the
final radix. Sort keys are descending digit sum, descending reading value, then
ascending original index (zero-based position in the `readings` array). Keep
the first `witness_k` entries after sorting (or all readings if fewer exist).

Digit sums use absolute values for negative readings (the bundled fixtures are
non-negative).

`lane_witnesses.json` contains `lanes`, sorted by `lane_id`, each with
`witnesses` rows sorted by the same lane-local ranking order (the kept prefix
of the sorted list).

`merged_rank.json` contains `witnesses`, the concatenation of every kept row
from every remaining lane, globally sorted by descending `digit_sum`,
descending `reading`, ascending `lane_id`, then ascending `index`.

## Outputs

Write to audit root (default `/app/dwr_audit/`):

1. `lane_witnesses.json` as described.
2. `merged_rank.json` as described.
3. `incident_trail.json` with `applied` (array in processing order) and
   `ignored` (integer count).
4. `summary.json` with integer fields sorted lexicographically by key when
   emitted: `applied_incidents`, `current_day_used`, `ignored_incidents`,
   `incident_day_floor_used`, `merged_witness_count`, `radix_final`,
   `suppressed_lane_count`, `total_readings` where `total_readings` sums
   reading counts across all non-suppressed lanes after incidents.
