# Output Format

Every output file is the byte-exact result of the canonical Python
serializer:

    json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"

Concretely: object keys are lexicographically sorted at every depth,
arrays render multiline (one element per line, two-space indent),
strings escape every non-ASCII byte as `\uXXXX`, and every file ends
with exactly one trailing line feed. Empty arrays and empty objects
render compact (`[]` and `{}`).

## `filter_state.json`

```
{
  "counter_bits": <int>,
  "counters": [<int>, <int>, ..., <int>],   // length m, in index order 0..m-1
  "k": <int>,
  "m": <int>,
  "stats": {
    "clamped_remove":     <int>,
    "clears":             <int>,
    "rejected_negative":  <int>,
    "rejected_saturate":  <int>,
    "resizes":            <int>,
    "successful_adds":    <int>,
    "successful_queries": <int>,
    "successful_removes": <int>
  }
}
```

`m`, `k`, and `counter_bits` are the values *at end of replay* (so a
late `resize` is reflected). `counters` is the final counter array in
index order, length `m`.

## `query_log.json`

```
{
  "queries": [
    {
      "actual":    true | false,            // ground-truth from multiset_count
      "key":       <string>,                // resolved key string
      "outcome":   "tp" | "fp" | "tn" | "fn",
      "predicted": true | false,            // counter-based prediction
      "seq":       <int>
    },
    ...
  ]
}
```

Entries are in `seq` order (which is the order they appeared in
`events.json`).

## `event_log.json`

```
{
  "events": [
    {
      "code": <string>,                     // closed code from /app/docs/diagnostics.md
      "key":  <string> | null,              // null for clear / resize / dump_stats
      "op":   <string>,                     // verbatim event op
      "seq":  <int>
    },
    ...
  ]
}
```

Length matches `events.json["events"]` exactly: every input event yields
exactly one event-log entry.

## `stats_dumps.json`

```
{
  "dumps": [
    {
      "counter_bits":     <int>,
      "k":                <int>,
      "m":                <int>,
      "non_zero_slots":   <int>,
      "saturated_slots":  <int>,
      "seq":              <int>,
      "stats": {
        "clamped_remove":     <int>,
        "clears":             <int>,
        "rejected_negative":  <int>,
        "rejected_saturate":  <int>,
        "resizes":            <int>,
        "successful_adds":    <int>,
        "successful_queries": <int>,
        "successful_removes": <int>
      },
      "total_count":      <int>             // sum of all counter values, in [0, m * (2^counter_bits - 1)]
    },
    ...
  ]
}
```

`non_zero_slots` is the count of counter slots whose current value is
> 0. `saturated_slots` is the count of slots currently at
`2^counter_bits - 1`. Both are taken at the moment of the
`dump_stats` event.

Entries are in `seq` order.

## `summary.json`

```
{
  "clamped_remove":     <int>,
  "clears":             <int>,
  "dumps_total":        <int>,
  "events_total":       <int>,
  "fn_count":           <int>,
  "fp_count":           <int>,
  "hot_keys": [
    {"key": <string>, "queries": <int>},
    ...
  ],
  "queries_total":      <int>,
  "rejected_negative":  <int>,
  "rejected_saturate":  <int>,
  "resizes":            <int>,
  "successful_adds":    <int>,
  "successful_queries": <int>,
  "successful_removes": <int>,
  "tn_count":           <int>,
  "tp_count":           <int>
}
```

`hot_keys` lists every key that received at least one `query` event
during the run. The list is sorted first by descending `queries` count,
then by ascending key (ASCII lexicographic) as a tie-break. Keys that
were never queried do not appear.
