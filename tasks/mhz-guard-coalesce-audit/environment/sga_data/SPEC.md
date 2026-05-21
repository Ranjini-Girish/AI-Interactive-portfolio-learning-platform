# Spectrum guard coalesce audit

All paths below are rooted at the task data directory mounted read-only in the container.

## Inputs

Read `policy.json`, `pool_state.json`, and `incident_log.json` at the data root. Enumerate every `*.json` file directly under `bins/` (non-recursive) and parse each as one bin record.

### Bin record

Each bin JSON object carries string `id`, integer half-open span `lo_mhz` and `hi_mhz` with `lo_mhz < hi_mhz`, string `tier` drawn from `production`, `staging`, or `lab`, and integer `occupancy` (non-negative).

### Policy

`policy.json` supplies integer `merge_gap_mhz` (non-negative), integer `heat_floor` (non-negative), and boolean `hot_only_merge`.

### Pool snapshot

`pool_state.json` supplies integer `snapshot_day`. Incidents with `day` strictly greater than `snapshot_day` are ignored for mutation and counted only toward ignored totals.

### Incidents

`incident_log.json` is an array of objects, each with string `event_id`, integer `day`, string `kind`, and optional fields `bin_id` (string), `delta` (integer), or `floor_delta` (integer) depending on `kind`.

Sort the full incident list ascending by `day`, then by `event_id` (UTF-8 byte order). Walk that order once. For each incident, if `day` exceeds `snapshot_day`, increment ignored and continue. Otherwise apply the first matching rule below; if none match, increment ignored and continue.

- `relax_heat` requires `floor_delta` present and non-negative. Decrease the working `heat_floor` by `floor_delta`, clamping at zero. Append one applied record.
- `strip_bin` requires `bin_id` present. If no active bin has that `id`, increment ignored. Otherwise remove that bin from the active set and append one applied record.
- `tighten_gap` requires `delta` present and non-negative. Subtract `delta` from the working `merge_gap_mhz`, clamping at zero. Append one applied record.
- Any other `kind` increments ignored only.

Applied trail entries are objects with keys `day`, `event_id`, `kind`, and `detail`. The `detail` object holds only keys relevant to the mutation: `heat_floor` after `relax_heat`, `bin_id` after `strip_bin`, or `merge_gap_mhz` after `tighten_gap`. Integer values in `detail` reflect the post-mutation working numbers.

## Coalescing after incidents

Let the working `merge_gap_mhz`, `heat_floor`, and `hot_only_merge` be the post-incident values. Build the active bin list from bins still present after `strip_bin` removals.

Sort bins ascending by `lo_mhz`, then by `id`. Repeatedly scan left to right, merging the current run with the immediate next bin while a merge predicate holds. After a pass that performs at least one merge, scan again until a full pass makes no merges.

Adjacency uses sorted order: the candidate right bin is the next array element after the current fused block. The gap between a left bin `L` and right bin `R` is zero when `R.lo_mhz < L.hi_mhz` (overlap), otherwise `R.lo_mhz - L.hi_mhz`. A merge is allowed only when `L.tier == R.tier`, the gap is less than or equal to the working `merge_gap_mhz`, and either `hot_only_merge` is false or both sides have `occupancy` greater than or equal to the working `heat_floor`. When coalescing, the fused span uses the minimum `lo_mhz`, maximum `hi_mhz`, the shared `tier`, and the minimum `occupancy` across every original bin id participating on either side. Bin identities accumulate: split any fused `id` on `+`, union the two sides' ids, sort unique ids ascending, and join with single `+` characters.

## Outputs under the audit directory

Write four UTF-8 JSON files with ASCII-only text, recursively sorted object keys at every object, comma separators without spaces between tokens, no trailing spaces on lines, and exactly one trailing newline at end of file.

### segments.json

Top-level object with key `segments`, an array of segment objects sorted by `lo_mhz` ascending, then `tier`, then the joined `bin_ids` string formed by joining sorted ids with `+`. Each segment lists integer `lo_mhz`, integer `hi_mhz`, integer `width_mhz` equal to `hi_mhz - lo_mhz`, string `tier`, and `bin_ids` as a sorted array of strings.

### incident_trail.json

Object with integer `ignored` count and `applied` array containing the applied records in chronological processing order (the sorted walk order).

### tier_rollup.json

Object with key `tiers`, an array sorted by `tier` name ascending. Each element has string `tier`, integer `width_mhz` (sum of `width_mhz` for segments of that tier), and integer `bins` (total count of bin ids across segments of that tier, counting multiplicity inside each segment).

### summary.json

Object with integer fields `snapshot_day`, `segments` (segment count), `total_active_bins` (sum of bin id counts across all segments), `applied_incidents`, `ignored_incidents`, `final_gap_mhz`, and `final_heat_floor`.
