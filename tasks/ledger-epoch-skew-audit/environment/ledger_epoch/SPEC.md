# Ledger epoch skew audit

All JSON written by the audit uses UTF-8, two-space indent, ASCII-only text, object keys sorted lexicographically at every object level, and a single trailing newline after the closing value. Arrays preserve the order mandated below; do not sort arrays unless the spec explicitly says to sort.

## Input layout

- Read `incidents/active.json` first. It contains string `incident_id`, integer `skew_slack` (>= 0), arrays of strings `waived_skew_child_ids`, `released_hold_ids`, `forced_quarantine`, and `transitive_exempt_children`. Unknown fields are ignored.
- Read every `segments/*.json` file in the `segments` directory (non-recursive). Each segment object must include string `segment_id`, integers `writer_epoch`, `record_epoch_low`, `record_epoch_high`, boolean `compaction_hold`, string `hold_id` (empty string allowed), boolean `base_quarantine`, and optional `parent_segment_id` (either absent, JSON null, or a string). Unknown fields are ignored. Each `segment_id` appears in at most one file.

## Merge order

Let `S` be the set of all loaded `segment_id` values. Emit `merge_order.json` with a single key `ordered_segment_ids`: the elements of `S` sorted by ascending `writer_epoch` from the segment record, then ascending ASCII `segment_id` as the tie-breaker.

## Quarantine closure

Let `B` be the set of segment ids where `base_quarantine` is true in the segment file, union the set `forced_quarantine` from the incident (treat as forced base quarantine even if absent from files).

Initialize `Q = B`. Repeatedly scan every segment until a full pass makes no addition: for a segment `c` not yet in `Q`, let `p` be its `parent_segment_id`. If `p` is absent, null, or equal to `c`, do nothing for this edge. If `p` is not a loaded segment id, do nothing for propagation (skew will still report missing parent separately). Otherwise, if `p in Q` and `c` is not listed in `transitive_exempt_children`, add `c` to `Q`.

Emit `quarantine_closure.json` with keys in this order: `base_ids`, `forced_ids`, `quarantined_segment_ids`, `transitive_only_ids`. `base_ids` lists every id with `base_quarantine` true sorted ascending. `forced_ids` lists ids from `forced_quarantine` sorted ascending. `quarantined_segment_ids` lists all ids in `Q` sorted ascending. `transitive_only_ids` lists ids in `Q` that are not in `B`, sorted ascending.

## Epoch skew findings

For each segment `c`, if `record_epoch_low > record_epoch_high`, append one finding with `code` `internal_inversion`, `segment_id` equal to `c`, `parent_segment_id` JSON null, `detail` string `low_gt_high`, and integer `writer_epoch` copied from `c`.

Otherwise consider `parent_segment_id` when it is a non-null string `p` that is not equal to `c`. If `p` is not a loaded segment id, append finding `code` `missing_parent_ref`, `parent_segment_id` string `p`, `detail` string `unknown_parent`, and `writer_epoch` from `c`.

When `p` is a loaded segment id, let `P` be that parent record. Let `expected = P.record_epoch_high + 1`. Let `low_ok = expected - skew_slack` and `high_ok = expected + skew_slack` using the incident `skew_slack`. If `c.segment_id` appears in `waived_skew_child_ids`, skip parent-child skew checks for this pair. Otherwise, if `c.record_epoch_low < low_ok`, append finding `code` `epoch_behind` with `detail` string `low_below_window`. If `c.record_epoch_low > high_ok`, append finding `code` `epoch_ahead` with `detail` string `low_above_window`. Each skew finding object includes keys in this order: `code`, `detail`, `parent_segment_id` (JSON null or string `p`), `segment_id`, `writer_epoch`.

Sort the `findings` array by ascending `segment_id`, then ascending `code`, then ascending `detail`, then treating JSON null parent last before any string parent ascending.

## Compaction gates

For every segment with `compaction_hold` true, compute `gate_active`. When `hold_id` is the empty string, `gate_active` is true. Otherwise `gate_active` is false exactly when `hold_id` appears in `released_hold_ids`; it is true in every other case.

Emit `compaction_gates.json` with key `gates`, an array of objects sorted by ascending `segment_id`. Each object lists keys in this order: `gate_active`, `hold_id`, `segment_id`.

## Summary

Emit `summary.json` with integer fields only, keys sorted lexicographically: `active_compaction_gates` (count of gates with `gate_active` true), `epoch_skew_findings`, `quarantined_total`, `segments_loaded`, `transitive_quarantine_count` (size of `transitive_only_ids`), `writer_epoch_span` defined as `(max writer_epoch among loaded segments) - (min writer_epoch among loaded segments)` and `0` when fewer than two segments load.

## Output files under the audit directory

Write exactly these five files: `merge_order.json`, `epoch_skew.json`, `compaction_gates.json`, `quarantine_closure.json`, and `summary.json`.
