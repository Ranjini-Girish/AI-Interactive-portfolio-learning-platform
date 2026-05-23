# Output format

Five files are written into `<out_dir>`. All are canonical JSON:
UTF-8, ASCII-only `\uXXXX` escapes, two-space indent, recursively
sorted object keys at every depth, and exactly one trailing newline
character. The byte-exact target is the output of Python's

```
json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
```

Empty arrays and empty objects render compact (`[]`, `{}`); populated
arrays and objects render multiline.

## `cache_state.json`

```
{
  "b1": [{"entry_weight": <int>, "key": <string>}, ...],
  "b2": [{"entry_weight": <int>, "key": <string>}, ...],
  "p":  <int>,
  "t1": [{"cum_weight":   <int>, "key": <string>}, ...],
  "t2": [{"cum_weight":   <int>, "key": <string>}, ...]
}
```

Each list is the MRU->LRU sequence at the end of replay. Resident
lists (`t1`, `t2`) store `cum_weight` per entry; ghost lists (`b1`,
`b2`) store `entry_weight` per entry. `p` is the final value of the
adaptive parameter.

## `decisions.json`

```
{
  "decisions": [
    {
      "b1_size":          <int>,
      "b2_size":          <int>,
      "cum_weight_after": <int or null>,
      "dropped_from":     <string or null>,
      "dropped_key":      <string or null>,
      "dropped_weight":   <int or null>,
      "event_id":         <string>,
      "key":              <string or null>,
      "outcome":          <string>,
      "p_after":          <int>,
      "replaced_from":    <string or null>,
      "replaced_key":     <string or null>,
      "replaced_weight":  <int or null>,
      "t1_size":          <int>,
      "t2_size":          <int>,
      "type":             "access" | "evict" | "clear"
    },
    ...
  ]
}
```

Rows appear in input-event order, one per accepted event.

* `type` is the originating event type.
* `key` is the event's `payload.key` for `access`/`evict`, or `null`
  for `clear`.
* `outcome` is one of `hit_t1`, `hit_t2`, `ghost_hit_b1`,
  `ghost_hit_b2`, `miss`, `evicted`, `cleared`.
* `cum_weight_after` is the new `cum_weight` of the resident entry
  installed or updated by this `access` event; `null` for `evict`
  and `clear`.
* `replaced_key` / `replaced_from` / `replaced_weight` describe the
  entry demoted by the `REPLACE` subroutine (`"t1"` or `"t2"`,
  along with the demoted entry's `cum_weight` at demotion time).
  All three are `null` if no `REPLACE` ran for this event.
* `dropped_key` / `dropped_from` / `dropped_weight` describe a key
  fully dropped from the cache by the miss-case ghost or T1
  direct-drop branches (`"b1"`, `"b2"`, or `"t1"`). `dropped_weight`
  is the `entry_weight` for B1/B2 drops and the `cum_weight` for the
  T1 direct drop. All three are `null` otherwise.
* `t1_size, t2_size, b1_size, b2_size, p_after` reflect the state
  immediately after the event was applied.

## `event_audit.json`

```
{
  "events": [
    {
      "accepted":       <bool>,
      "event_id":       <string>,
      "payload":        <object>,
      "reason_ignored": <string or null>,
      "ts_unix_ms":     <int>,
      "type":           "access" | "evict" | "clear"
    },
    ...
  ]
}
```

Every event in the input log appears exactly once. Rows are sorted
by `event_id` byte order. `reason_ignored` is one of the documented
reject reasons when `accepted == false`, otherwise `null`. `payload`
is reproduced verbatim from the input event (including the `weight`
field on accesses).

## `violations.json`

```
{
  "violations": [
    <same row shape as event_audit, but only for accepted == false>
  ]
}
```

Sorted by `event_id`.

## `summary.json`

Object with exactly these integer-valued keys (sorted at depth):

* `total_events`
* `total_accesses`
* `total_evicts`
* `total_clears`
* `accesses_accepted`
* `evicts_accepted`
* `evicts_rejected`
* `clears_accepted`
* `clears_rejected`
* `hits_t1`
* `hits_t2`
* `ghost_hits_b1`
* `ghost_hits_b2`
* `misses`
* `total_distinct_keys`
* `total_weight_admitted`
* `final_p`
* `final_t1_weight_sum`
* `final_t2_weight_sum`
* `final_b1_weight_sum`
* `final_b2_weight_sum`

`total_distinct_keys` counts every key that has ever appeared in any
of T1/T2/B1/B2 during replay (including keys later dropped).
`total_weight_admitted` is the sum of `payload.weight` over every
accepted `access` event (every `access` event is accepted).
`final_p` matches `p` in `cache_state.json`. The four
`final_*_weight_sum` fields are the sums of `cum_weight` (for T1,
T2) or `entry_weight` (for B1, B2) over the entries present in each
list at the end of replay. `accesses_accepted` equals
`hits_t1 + hits_t2 + ghost_hits_b1 + ghost_hits_b2 + misses`.

## Atomic write contract

Every output file is staged first to `<name>.partial`, written
fully to disk, then `rename(2)`d to its final name. Renames happen
in alphabetical filename order: `cache_state.json`,
`decisions.json`, `event_audit.json`, `summary.json`,
`violations.json`. On any error during staging or renaming, every
`.partial` and every already-renamed final created during this run
must be removed before the binary exits non-zero. The binary must
refuse to start if any of the five final paths or `.partial`
siblings already exist (regular file, directory, symlink, or
anything else).
