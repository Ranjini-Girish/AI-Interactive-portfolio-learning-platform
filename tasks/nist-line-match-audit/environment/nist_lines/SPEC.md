# Optical line matching audit — normative contract

All JSON emitted under `/app/audit/` must be UTF-8, end with exactly one trailing newline, use two-space indentation, and sort object keys lexicographically at every depth. Arrays follow the sort orders stated below. Numbers are JSON numbers. Use `null` only where this document explicitly allows it.

## Inputs (read-only)

- `/app/nist_lines/pool_state.json` supplies integers `sigma_multiplier_milli` (strictly positive), `match_slack_nm` (non-negative), `weak_rel_int_threshold` (non-negative), `min_same_element_separation_nm` (strictly positive); number `min_amp_for_weak` (strictly positive); and array `element_tie_order` listing distinct non-empty element symbols in priority order (earlier wins ties).
- `/app/nist_lines/instruments.json` maps `instruments` objects keyed by `instrument_id` with integer `base_bias_nm` (may be negative).
- `/app/nist_lines/incident_log.json` lists `events` in file order. Each event has string `kind`, optional boolean `accepted` (default true when absent), optional integer `effective_day` (required for the kinds defined below when accepted), optional string `instrument_id`, optional string `line_id`, optional integer `delta_bias_nm`.
- `/app/nist_lines/catalog/*.json` each contain string `element` and array `lines`. Every line has string `line_id` (unique across every catalog file), integer `wave_nm` (non-negative), integer `rel_int` (non-negative), and string `label` (metadata only for humans).
- `/app/nist_lines/observations/*.json` each contain string `run_id`, string `instrument_id`, integer `run_day`, and array `peaks` in file order. Every peak has integer `peak_index` (distinct per file, starting at 0 ascending), integer `wave_nm`, number `sigma_nm` (strictly positive), and number `amp` (non-negative).

## Incident acceptance

An event is **accepted** when `accepted` is not boolean `false` and `kind` is one of `instrument_bias_shift` or `catalog_line_suppress`. Any other `kind`, or `accepted` equal to boolean `false`, is **ignored** and increments `summary.ignored_incidents`.

For `instrument_bias_shift`, an accepted event must carry non-empty `instrument_id` present under `instruments`, integer `effective_day`, and integer `delta_bias_nm`; otherwise it is ignored and increments `summary.ignored_incidents`.

For `catalog_line_suppress`, an accepted event must carry non-empty `line_id` matching some catalog line and integer `effective_day`; otherwise ignored and increments `summary.ignored_incidents`.

## Catalog construction

Load every `catalog/*.json`. Build the **catalog list** as all line objects augmented with their host `element`. Sort this list ascending by `(wave_nm, element, line_id)` for deterministic iteration when scanning.

A line is **suppressed on day** `d` when there exists an accepted `catalog_line_suppress` with that `line_id` and `effective_day` ≤ `d`. Suppressed lines are excluded from all matching for runs with `run_day` ≥ `effective_day` of that suppress event (per-event: each suppress stands alone; once active for a run day, it stays active).

## Instrument bias timeline

For each `instrument_id`, start from `base_bias_nm`. Process accepted `instrument_bias_shift` events in file order; when a run has `run_day` ≥ the event’s `effective_day` and the run’s `instrument_id` matches, add `delta_bias_nm` to that instrument’s running bias for that run. The **final bias** for a run is the sum of `base_bias_nm` plus every applicable shift event for that instrument whose `effective_day` ≤ `run_day`.

## Windowing

For a peak with `sigma_nm` and instrument-adjusted center `adj_wave_nm` (integer), define integer half-width `half = match_slack_nm + ceil((sigma_multiplier_milli * sigma_nm) / 1000.0)` using IEEE double arithmetic for the product and `math.Ceil` semantics for the outer ceil. A catalog line with `wave_nm` is **in-window** when `abs(line.wave_nm - adj_wave_nm) <= half`.

## Weak-line gate

A catalog line is **amp-eligible** for a peak when `rel_int` ≥ `weak_rel_int_threshold` or `amp` ≥ `min_amp_for_weak`.

## Blended gate

For a peak, take the set `S` of catalog lines that are not suppressed for the run day, are in-window, and are amp-eligible. If there exist two distinct lines in `S` with the same `element` such that `abs(wave_nm_a - wave_nm_b) < min_same_element_separation_nm`, the peak’s status is `blended_conflict` and no line is assigned.

## Matching selection

When `S` is non-empty and blended gate passes, discard any `line_id` already assigned to an earlier peak in the same run (earlier means lower `peak_index` in that file). Let `T` be the remaining lines. If `T` is empty, status is `unmatched` with no line.

Otherwise pick the single line in `T` minimizing `abs(line.wave_nm - adj_wave_nm)` as primary key. Tie-breakers in order: larger `rel_int`, smaller `wave_nm`, smaller index of `element` in `element_tie_order` (missing elements sort after listed ones by `element` string ascending), smaller `line_id` lexicographically. Assign that line; status is `matched`.

If `S` is empty because every in-window non-suppressed line failed amp-eligibility, but at least one in-window non-suppressed line exists ignoring amp, status is `weak_suppressed`. If no in-window non-suppressed line exists at all, status is `unmatched`.

## Outputs

### `run_matches.json`

Top-level key `runs`: sorted ascending by `run_id`. Each run object has `run_id`, `instrument_id`, `run_day`, and `peaks` sorted ascending by `peak_index`. Each peak has `peak_index`, `status` in `matched`, `unmatched`, `weak_suppressed`, `blended_conflict`, optional `line_id` (null unless `matched`), optional `catalog_wave_nm` (null unless `matched`), optional `delta_nm` (null unless `matched`; equals assigned `wave_nm - adj_wave_nm` as integer).

### `line_utilization.json`

Top-level key `lines`: one object per catalog `line_id` sorted by `line_id`, fields `line_id` and `match_count` (integer count of `matched` peaks referencing that line across all runs).

### `instrument_bias_state.json`

Top-level key `instruments`: sorted by `instrument_id`. Each object has `instrument_id`, `base_bias_nm`, `incident_delta_total_nm` (sum of accepted shift `delta_bias_nm` values that ever apply to any run in the dataset for that instrument), `final_bias_nm` (bias applied to the latest `run_day` observed for that instrument among the observation files).

If an instrument never appears in observations, omit it from this array.

### `suppressed_catalog.json`

Top-level key `entries`: sorted by `line_id`. Each object has `line_id`, `effective_day` taken from the accepted suppress event (if duplicates, smallest `effective_day`), `active_on_last_day` boolean true when that suppress applies on the maximum `run_day` found across observations.

### `summary.json`

Fields: `runs_processed` (count of observation files), `peaks_total`, counts `peaks_matched`, `peaks_unmatched`, `peaks_weak_suppressed`, `peaks_blended_conflict`, `ignored_incidents`, `catalog_lines_loaded` (count of lines), `max_run_day`.
