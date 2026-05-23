# Diagnostic Codes

`event_log.json` carries one entry per state-changing event in `seq`
order. The closed catalogue of diagnostic codes is exhaustive: every
event must record exactly one of these codes, and the verifier rejects
any output that introduces a code not in this list.

| Code                   | Severity | Fired by                                                                            |
|------------------------|----------|-------------------------------------------------------------------------------------|
| `D_OK_ADD`             | info     | `add` under `saturation_action == "saturate"`, or `"reject"` when no slot was at max |
| `D_REJECTED_SATURATE`  | warning  | `add` under `saturation_action == "reject"` when at least one slot was already at max |
| `D_OK_REMOVE`          | info     | `remove` under `remove_below_zero_action == "clamp"` when no slot was at zero, or under `"reject"` when no slot was at zero |
| `D_CLAMPED_REMOVE`     | warning  | `remove` under `remove_below_zero_action == "clamp"` when at least one slot was already at zero |
| `D_REJECTED_NEGATIVE`  | warning  | `remove` under `remove_below_zero_action == "reject"` when at least one slot was already at zero |
| `D_OK_QUERY`           | info     | `query` (always) — the outcome is recorded in `query_log.json`, not in this code |
| `D_OK_CLEAR`           | info     | `clear` |
| `D_OK_RESIZE`          | info     | `resize` |
| `D_OK_DUMP`            | info     | `dump_stats` |

## What `event_log.json` contains

`event_log.json` is one entry per replayed event, in `seq` order. Each
entry is the four-field object documented in
`/app/docs/output_format.md`:

```
{
  "key":  <string|null>,   // resolved key string, or null when the event has no key_idx
  "op":   <string>,         // the event op, verbatim from the input
  "seq":  <int>,            // the event seq, verbatim from the input
  "code": <string>          // exactly one of the diagnostic codes above
}
```

The `key` field is `null` for `clear`, `resize`, and `dump_stats` (those
events have no `key_idx`). For `add`, `remove`, and `query` it is the
resolved key string from `keys.json`.

## What `query_log.json` carries

`query_log.json` is exclusively for `query` events; `add` / `remove` /
`clear` / `resize` / `dump_stats` events do not appear there. The
chronological order matches `seq`.

`event_log.json` and `query_log.json` are independent: a `query` event
appears in BOTH (with `D_OK_QUERY` in the event log and the
`tp` / `fp` / `tn` / `fn` outcome in the query log). Diagnostic codes
never appear in `query_log.json`.

## What `summary.json` aggregates

`summary.json` aggregates the per-event outcomes into one document per
run. The exhaustive field list lives in `/app/docs/output_format.md`;
the noteworthy invariants are:

- `summary.events_total` equals the size of `events.json["events"]`.
- `summary.events_total` equals the size of `event_log.json["events"]`
  (every input event produces one event-log entry).
- `summary.queries_total` equals the size of `query_log.json["queries"]`
  and is the count of `query` events in the input.
- `summary.tp_count + summary.fp_count + summary.tn_count +
  summary.fn_count == summary.queries_total`.
- `summary.dumps_total` equals the size of
  `stats_dumps.json["dumps"]` and is the count of `dump_stats` events in
  the input.
