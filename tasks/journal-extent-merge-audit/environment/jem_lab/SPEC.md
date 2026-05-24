# Journal extent merge laboratory — normative specification

## Scope
All relative paths below live under `/app/jem_lab/`. The audit reads this bundle only and writes exactly two files under `/app/audit/`: `merged_extents.json` and `summary.json`.

## Inputs
- `policy.json` defines `active_volumes` (array of volume identifiers), `volumes` (map of volume id to `{ "gap_merge_max": <int>, "byte_ceiling": <int> }`), and optional integer `cross_volume_guard` (default `0`, unused by the reference but must be parsed if present).
- `pool_state.json` contains integer `journal_seq` copied into the summary.
- `incident_log.json` contains ordered `events`.
- `anchors/guard.json` contains `{ "watch": [ <extent ids> ] }` used only to count how many emitted extents correspond to watched ids after merging (watch hits are counted on merged ids that equal a watched id or that absorbed a watched id through merge — see below).
- `ancillary/notes.json` contains optional string field `tag` echoed into summary.
- `extents/ext_XX.json` for `XX` from `00` to `17` inclusive — each file is one extent object `{ "id": <str>, "vol": <str>, "start": <int>, "end": <int>, "bytes": <int> }` using half-open intervals `[start, end)`.

## Incident replay
Process `events` in array order. `applied_events` counts every object. Supported kinds:
1. `delete_extent` with `id` string — removes any extent with that id.
2. `shrink_end` with `id` and integer `new_end` — sets `end = new_end`; if `new_end <= start` afterward, remove the extent.

Filtering to `active_volumes` happens **before** incidents.

## Merge algorithm
After incidents, partition remaining extents by `vol`. Ignore extents whose `vol` is not listed in `active_volumes`.

For each active volume independently:
1. Sort extents by `(start ascending, id ascending)`.
2. Initialize an empty output list `out`.
3. Walk the sorted list left-to-right maintaining a cursor `cur`. The first extent seeds `cur`.
4. Let `gap` be `policy.volumes[vol].gap_merge_max`. While a next extent `nxt` exists, if `nxt.start - cur.end <= gap`, merge: set `cur.end = max(cur.end, nxt.end)`, `cur.bytes += nxt.bytes`, and `cur.id` to the lexicographically smaller of the two ids (strict `<` on UTF-8 codepoint order as Python compares strings). Continue attempting to merge the following extent into the same `cur` until the gap rule fails, then append `cur` to `out` and seed a new `cur` from `nxt`.
5. After forming each merged `cur`, if `cur.bytes` exceeds `byte_ceiling` for that volume, replace `bytes` with `byte_ceiling` and set boolean `capped` true on that merged record; otherwise `capped` is false.

## Watch hits
Let `watch` be the array in `anchors/guard.json` (default empty if missing). After merges, count a hit whenever a merged extent’s final `id` equals an element of `watch` **or** the merge absorbed at least one pre-merge extent whose original `id` was in `watch`, even if the merged id changed to a different survivor string. Each merged extent contributes at most one hit.

## Outputs
### merged_extents.json
```json
{
  "volumes": {
    "V0": [ { "id": "...", "start": 0, "end": 0, "bytes": 0, "capped": false } ],
    "V1": [ ... ]
  }
}
```
Include every active volume key in ascending order even if the array is empty.

### summary.json
```json
{
  "applied_events": <int>,
  "journal_seq": <int>,
  "merged_extent_count": <int>,
  "tag": "<string>",
  "watch_hits": <int>
}
```
`merged_extent_count` totals merged extents across all active volumes. `tag` comes from `ancillary/notes.json["tag"]` when it is a string, else empty string.

## On-disk JSON encoding
Write with `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` plus a trailing newline.
