# Output Format

Write exactly one UTF-8 JSON object to the `--out` path with:
- **Two-space indentation** (`indent=2`).
- **Keys sorted alphabetically** at every object level (`sort_keys=True`).
- A **single trailing newline** after the closing `}`.
- No carriage returns (`\r`).

This matches Python's `json.dumps(obj, indent=2, sort_keys=True) + "\n"`.
Numeric output fields are rounded to **six** decimal places; integers remain integers
and absent values are JSON `null`.

Top-level keys: `schema_version`, `summary`, `events`, `findings`.

`schema_version` is the integer `1`.

## Summary

`summary` has keys: `by_finding_type`, `by_severity`, `event_count`, `excluded_events`,
`findings_count`, `localized_events`, `mean_magnitude`, `station_count`,
`total_picks_used`, `total_rejected_picks`.

- `by_severity` always contains **all five** severity keys (`critical`, `high`, `medium`,
  `low`, `info`), even when the count is zero.
- `by_finding_type` contains only finding types that actually occurred (zero-count types
  are omitted).
- `mean_magnitude` is the mean of all localized-event `ml` values that are non-null,
  rounded to 6 decimals. If no events have a non-null `ml`, it is `null`.
- `station_count` is the **total number of rows** in `network/stations.csv`, including
  disabled stations. It does not depend on which stations were used.
- `excluded_events` is the count of events whose output `status` is `"excluded"`.

## Events Array

`events` is sorted by `event_id`. Each event object has keys: `azimuth_gap_deg`,
`depth_km`, `event_id`, `findings`, `ml`, `ml_uncertainty`, `nearest_station_km`,
`origin_time_s`, `phase_counts`, `rejected_pick_count`, `rms_residual_s`,
`source_pick_ids`, `status`, `used_pick_count`, `x_km`, `y_km`.

- The `status` field must be one of these exact strings:
  - `"localized"` — event was successfully localized via grid search.
  - `"excluded"` — event's status in `events.csv` is `"exclude"` or `"void"`, or its
    `event_id` appears in `exclusions.json → excluded_events`.
  - `"insufficient_picks"` — processable event has fewer than `min_usable_picks` eligible
    picks (no localization attempted).
  - `"failed"` — grid search produced no valid solution (e.g., no velocity layer covers
    any candidate position). Treat identically to `"insufficient_picks"` for null-field
    rules; no finding is emitted for the failed status itself.
- Excluded or insufficient-picks events use `null` for location, origin, RMS, azimuth gap,
  nearest station, and magnitude fields.
- `used_pick_count` is the number of picks in `source_pick_ids` (picks used in the final
  grid-search solution, after any residual-rejection rerun). For excluded and
  insufficient-picks events this is always `0`.
- `rejected_pick_count` = (total raw picks for this event) − `used_pick_count`.
  Concretely: every pick that appears in `picks.csv` for this event that is **not** in
  `source_pick_ids` counts as rejected — whether it was ineligible, residual-rejected, or
  simply not used because the event could not be localized.
- `phase_counts` reflects only **used picks** (`source_pick_ids`). It always has both `"P"`
  and `"S"` integer keys, even if zero. It does not count eligible-but-not-used or
  rejected picks.
- `source_pick_ids` is sorted lexicographically and contains only pick IDs used in the
  final solution.
- Per-event `findings` contains the **full finding objects** (same structure as the
  top-level `findings` array — see below). It must **not** be a list of type-name
  strings. Example of a single per-event finding entry:
  ```json
  {
    "event_id": "EV001",
    "evidence": {"depth_km": 0.5, "threshold_km": 2.0},
    "finding_type": "shallow_depth",
    "pick_id": null,
    "severity": "medium",
    "severity_rank": 3,
    "station_id": null
  }
  ```
- Per-event `findings` entries appear in **generation order** (the order the pipeline
  produces them during processing): ineligible-pick findings first, then QC findings
  in the sequence they are checked. They are **not** re-sorted into the global sort
  order. Only the top-level `findings` array is sorted.

## Findings Array

`findings` (top-level) is sorted by: `severity_rank` descending, then `finding_type`,
`event_id`, `station_id`, `pick_id` ascending. Null identifiers sort as the empty
string.

Each finding has keys: `event_id`, `evidence`, `finding_type`, `pick_id`, `severity`,
`severity_rank`, `station_id`.
