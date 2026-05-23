# Output Format

Four files in `/app/output/`. Every file is the byte-exact result of
Python's `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) +
"\n"`. That is: arrays render multiline (one element per line, two-space
indent), object keys are lexicographically sorted at every depth, all
non-ASCII bytes are escaped as `\uXXXX`, and every file ends with a
single LF newline. Empty arrays and objects render compact (`[]`, `{}`).
Integer values stay integers; booleans stay booleans.

## `sa_state.json`

```
{
  "sas": [
    {
      "accepted":    <int>,
      "bitmap":      <hex_str>,    // see window.md for the encoding
      "id":          <str>,
      "owner":       <str>,
      "recv_total":  <int>,
      "rekeys":      <int>,
      "replays":     <int>,
      "too_old":     <int>,
      "top":         <int>,
      "window_size": <int>
    },
    ...
  ]
}
```

Sorted by `id` ASCII ascending. Includes every SA currently present in the
live table at trace end (deleted SAs do not appear here). Per-SA counters
are lifetime values: they accumulate across `rekey` events and DO NOT
reset.

## `packet_decisions.json`

```
{
  "decisions": [
    {
      "decision":          <str>,         // see decision-value table below
      "diagnostic":        <str|null>,    // diagnostic code emitted by THIS recv, or null
      "esp_seq":           <int>,
      "passive_created":   <bool>,        // true iff this row created a passive SA
      "sa_id":             <str>,
      "seq":               <int>          // the event seq from events.json
    },
    ...
  ]
}
```

Chronological by `seq` (no sorting beyond the natural input order). One
row per `recv` event in `events.json`. The `decision` field takes one of:

| `decision`         | When                                                                                  |
|--------------------|---------------------------------------------------------------------------------------|
| `accept`           | normal accept (branch 2 with the SA already present, or branch 4 with bit clear).     |
| `accept_passive`   | unknown SA under `create_passive`; passive SA created and packet accepted.            |
| `replay_logged`    | replay branch under `on_replay == "log_only"`. `diagnostic` is `"W_REPLAY"`.          |
| `replay_dropped`   | replay branch under `on_replay == "drop"`. `diagnostic` is `"W_REPLAY"`.              |
| `too_old_logged`   | too-old branch under `on_too_old == "log_only"`. `diagnostic` is `"W_TOO_OLD"`.       |
| `too_old_dropped`  | too-old branch under `on_too_old == "drop"`. `diagnostic` is `"W_TOO_OLD"`.           |
| `unknown_drop`     | unknown SA under `on_unknown_sa == "drop"`. `diagnostic` is `"E_UNKNOWN_SA"`.         |

For `accept` (no passive create), `diagnostic` is `null` and
`passive_created` is `false`. For `accept_passive`, `diagnostic` is
`"N_PASSIVE_CREATED"` and `passive_created` is `true`.

## `replay_log.json`

```
{
  "entries": [
    { "decision": <str>, "diagnostic": <str>, "esp_seq": <int>,
      "sa_id": <str>, "seq": <int> },
    ...
  ]
}
```

Chronological by `seq`. Contains exactly the subset of
`packet_decisions.decisions` whose `decision` is one of `replay_logged`,
`replay_dropped`, `too_old_logged`, `too_old_dropped`, or `unknown_drop`.
`accept` and `accept_passive` rows are NOT included. The `diagnostic`
field is never `null` here (every excluded decision carries a
diagnostic).

## `summary.json`

```
{
  "accepted_total":           <int>,   // sum across SAs ever observed of their lifetime "accepted"
  "active_sa_count":          <int>,   // number of SAs in the live table at trace end
  "add_sa_failures":          <int>,   // add_sa events that emitted an error diagnostic
  "drop_unknown_sa":          <int>,   // recv events with decision == "unknown_drop"
  "hot_sas": [                          // see "hot_sas selection" below
    {
      "id":         <str>,
      "replays":    <int>,
      "too_old":    <int>
    },
    ...
  ],
  "passive_created_count":    <int>,   // recv events with decision == "accept_passive"
  "policy_on_replay":         <str>,   // echoed verbatim from policy.json
  "policy_on_too_old":        <str>,   // echoed verbatim from policy.json
  "policy_on_unknown_sa":     <str>,   // echoed verbatim from policy.json
  "rekey_failures":           <int>,   // rekey events that emitted an error diagnostic
  "rekey_successes":          <int>,   // rekey events that did NOT emit a diagnostic
  "replays_total":            <int>,   // recv events whose decision is "replay_*"
  "too_old_total":            <int>,   // recv events whose decision is "too_old_*"
  "total_events":             <int>    // events.length (every kind, not just recv)
}
```

`accepted_total` is the SUM of the per-SA `accepted` counter across every SA
id that was ever observed (including ids whose SA has been deleted by trace
end). Because an id cannot be re-added once observed, this sum is well
defined.

### `hot_sas` selection

`hot_sas` lists SAs whose lifetime `replays + too_old` is `>=
policy.min_hot_threshold` AND `> 0`. SAs whose sum is `0` are NEVER listed
even when `min_hot_threshold == 0`. The list is sorted by `(replays +
too_old)` descending, with ties broken by `id` ASCII ascending. The list
covers every observed SA id (even ids whose SA has been deleted -- the
counters are per-id, not per-current-SA).
