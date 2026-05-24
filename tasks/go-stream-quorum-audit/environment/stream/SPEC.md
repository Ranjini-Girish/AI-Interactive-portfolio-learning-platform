All tick values are integers on a shared timeline. Inputs are UTF-8 JSON under `/app/stream/` only:

- `quorum.json`: object with positive integer `threshold`.
- `policy.json`: object with non-negative integers `watermark`, `cutoff`, and `grace`.
- `manifest.json`: object with array `slices`. Process that array left to right. Only string elements name files under `/app/stream/slices/`. Missing slice files are treated as empty arrays. Malformed JSON in a slice file is treated as an empty array.
- Each slice file is a JSON array, possibly empty. Non-object array elements are ignored.

An accepted vote row is an object with non-empty string `stream`, non-empty string `voter`, string `phase` equal to `prepare` or `commit`, integers `epoch` (>= 0), `tick`, and `weight` (>= 1), optional boolean `late` default false, and optional boolean `escrow` default false. Reject rows with missing fields, wrong types, or invalid values.

Twist 1: watermark gate. Count every object row from every parsed slice in `summary.rows_seen` before applying drop rules. If `tick < policy.watermark` and `late` is not true, drop the row and increment `summary.rows_dropped_watermark`.

Twist 2: voter dedupe. Within each `(stream, epoch, voter)` triple keep the row with the largest `tick`. If `tick` ties, keep the row from the slice file encountered later while walking `manifest.json` left to right. Increment `summary.rows_deduped` once for every discarded duplicate row.

Twist 3: phase groups. Partition deduped rows by `(stream, epoch, phase)`. For each group let `weight_sum` be the sum of `weight` across members and `voters` the member `voter` strings sorted in ASCII order. Let `counted_sum` be the sum of `weight` only for members with `tick >= policy.watermark`. Evaluate every `prepare` group first: each phase entry's `status` is `quorum` when that group's `counted_sum >= quorum.threshold`, otherwise `open`. A `(stream, epoch)` pair is prepare-quorate only when its prepare entry's `status` is `quorum` and either `epoch` is `0` or `(stream, epoch - 1)` is already prepare-quorate.

Twist 4: commit escrow gate. For each `commit` group, if its `(stream, epoch)` is prepare-quorate then `counted_sum` uses the same `tick >= policy.watermark` filter as twist 3. Otherwise `counted_sum` is the sum of `weight` only for members with `escrow` true and `tick >= policy.watermark`. `status` is `quorum` when `counted_sum >= quorum.threshold`, otherwise `open`. `summary.groups_total` is the number of phase groups. `summary.groups_quorum` counts groups with status `quorum`.

Twist 5: stale open ballots. For every group with status `open`, for each member where `tick + policy.grace < policy.cutoff`, append one object to `stale` with keys `code`, `epoch`, `phase`, `stream`, `tick`, and `voter`, except skip members with `escrow` true when the group phase is `commit` and its `(stream, epoch)` is not prepare-quorate. `code` is always `LATE_TICK`. `summary.stale_logged` counts stale objects.

`ballots` is sorted by `stream` then `epoch`. Each element has keys `epoch`, `phases`, and `stream`. `phases` is sorted by phase name ascending. Each phase entry is a four-element array `[phase, status, weight_sum, voters]`.

`decisions` lists every group with status `quorum` as objects with keys `counted_sum`, `epoch`, `phase`, and `stream`, sorted by `stream`, then `epoch`, then `phase`.

`stale` is sorted by `stream`, then `epoch`, then `phase`, then `voter`, then `tick`.

`summary` has exactly these integer keys: `groups_quorum`, `groups_total`, `rows_deduped`, `rows_dropped_watermark`, `rows_seen`, `stale_logged`.

Write `/app/audit/report.json` with exactly four top-level keys: `ballots`, `decisions`, `stale`, and `summary`. Encode as UTF-8 JSON with two-space indentation, ASCII-only text, sorted object keys at every object level, and no trailing newline.
