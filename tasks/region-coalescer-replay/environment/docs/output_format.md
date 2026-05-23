# Output Format

Five files in `/app/output/`. Every file is canonical JSON: UTF-8, ASCII-only
escaping (`ensure_ascii=True`), two-space indent, object keys lex-sorted at
every depth, single trailing newline. Integer values stay integers (do not
emit them as JSON numbers with a decimal point); booleans stay booleans; the
empty list is `[]` not `null`.

## `region_state.json`

```
{
  "regions": [
    { "base": <int>, "id": <str>, "owner": <str>, "prot": <str>, "size": <int> },
    ...
  ]
}
```

Sorted by `(base, id)`. Includes every region currently mapped at trace end.

## `coalesce_log.json`

```
{
  "coalesces": [
    { "dropped_id": <str>, "kept_id": <str>, "seq": <int>, "trigger": "map" | "unmap" },
    ...
  ]
}
```

Chronological. Two cascading merges from a single `map` produce two records
with the same `seq` and `trigger == "map"`, in low-then-high order.

## `region_diagnostics.json`

```
{
  "events": [
    {
      "diagnostics": [
        { "code": <str>, "region_id": <str|null>, "severity": "error"|"warning"|"note" },
        ...
      ],
      "seq": <int>
    },
    ...
  ]
}
```

Outer list sorted by `seq` ascending; only events with at least one
diagnostic appear. Inner list sorted by `(severity_rank, code, region_id)`
with `severity_rank` = `0,1,2` for `error,warning,note` and `null` sorting
as the empty string.

## `region_graph.json`

```
{
  "cycles": [ [<id>, ...], ... ],
  "edges": [ { "from": <str>, "to": <str> }, ... ],
  "nodes": [ { "id": <str>, "in_degree": <int>, "out_degree": <int> }, ... ]
}
```

See `lineage.md` for what fills these. When `policy.track_history` is false
all three arrays are `[]`.

## `summary.json`

```
{
  "auto_coalesces":          <int>,   // length of coalesce_log.coalesces
  "events_with_diagnostics": <int>,   // length of region_diagnostics.events
  "explicit_merges":         <int>,   // successful "merge" ops only
  "final_region_count":      <int>,   // length of region_state.regions
  "maps_rejected":           <int>,   // "map" ops that emitted ANY error diagnostic
  "maps_succeeded":          <int>,   // "map" ops that ended up adding the region
  "owners":                  [<str>], // sorted ASCII, distinct owners with >=1 region at end
  "splits":                  <int>,   // successful "split" ops only
  "total_events":            <int>,   // events_in.length
  "unmaps_succeeded":        <int>    // "unmap" ops that actually removed a region
}
```

`maps_succeeded + maps_rejected` equals the total `map` event count. An
`overlap_action == "replace"` map that succeeds (after evicting overlapping
regions) counts as `maps_succeeded`, not `maps_rejected`, even though it
emitted `W_REPLACED_OVERLAP` warnings -- warnings do not count an event as
rejected. Only `error`-severity diagnostics on a `map` count as a rejection.
