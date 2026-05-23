# Canonical Output Format

Every output file under `/app/output/` must be:

- UTF-8 encoded,
- ASCII-only (every codepoint < 0x80; `ensure_ascii=True` in Python
  terminology, `nlohmann::json::dump(2, ' ', /*ensure_ascii=*/true)` in C++),
- 2-space indented,
- with object keys sorted lexicographically at every depth,
- terminated by exactly one trailing newline (`\n`).

Two consecutive runs of the binary against the same `/app/data/` MUST
produce byte-identical files. The verifier diffs SHA-256 hashes across runs
and across its own live-recomputed reference; the slightest formatting
deviation is a hard failure.

## `process_state.json`

```
{
  "processes": [
    {
      "cmdline": <str>,
      "exit_code": <int> | null,
      "exit_signal": <str> | null,
      "exit_tick": <int> | null,
      "pid": <int>,
      "ppid": <int>,
      "start_tick": <int>,
      "state": "RUNNING" | "ZOMBIE" | "EXITED",
      "uid": <int>
    },
    ...
  ]
}
```

- `processes` is sorted by `pid` ascending.
- A process never appears more than once.
- For `state == "RUNNING"`, all of `exit_code`, `exit_signal`, and
  `exit_tick` are `null`.
- For `state == "ZOMBIE"`, exactly one of `exit_code` or `exit_signal` is
  non-null and `exit_tick` is non-null.
- For `state == "EXITED"`, the exit fields are whatever they were at the
  moment of the zombie transition (carried through into EXITED unchanged).

## `reap_log.json`

```
{
  "reaps": [
    {
      "parent_pid": <int>,
      "pid": <int>,
      "seq": <int>,
      "tick": <int>,
      "trigger": "wait" | "init_reap"
    },
    ...
  ]
}
```

- `reaps` is the chronological log of reaps, NOT sorted - records are
  appended as the simulator processes the events.
- A `wait` event that successfully reaps a zombie appends a record with
  `trigger == "wait"` and `parent_pid` set to the wait issuer.
- An init auto-reap (under `policy.implicit_init_reap == true`) appends a
  record with `trigger == "init_reap"` and `parent_pid` set to
  `policy.init_pid`.
- When an event causes multiple init-reaps in the same handler (e.g. an
  exit whose zombie children are all reparented to init and then
  auto-reaped), the records appear in pid-ascending order within that
  event's `seq`.

## `process_diagnostics.json`

```
{
  "events": [
    {
      "diagnostics": [
        {"code": <str>, "pid": <int> | null, "severity": <str>},
        ...
      ],
      "seq": <int>
    },
    ...
  ]
}
```

- `events` is sorted by `seq` ascending and is sparse (only events that
  emitted at least one diagnostic appear).
- Within an event, `diagnostics` is sorted by
  `(severity_rank, code, pid)`. `severity_rank` is `0` for `error`, `1`
  for `warning`, `2` for `note`. `pid` sorts as integer; `null` is treated
  as smaller than every integer.
- `pid` is `null` only for `E_NOT_ZOMBIE` raised by a `wait` whose
  `target_pid` is `null`. Every other code carries a non-null integer
  `pid`.
- `severity` is the literal string `"error"`, `"warning"`, or `"note"`.

## `lineage_graph.json`

See `lineage.md`. Schema in summary:

```
{
  "cycles": [
    [<int>, <int>, ...],
    ...
  ],
  "edges": [
    {"from": <int>, "to": <int>, "type": <str>},
    ...
  ],
  "nodes": [
    {"id": <int>, "in_degree": <int>, "out_degree": <int>},
    ...
  ]
}
```

`type` is one of `"fork"` or `"reparent_init"`. When
`policy.track_lineage` is false, all three arrays are empty.

## `summary.json`

```
{
  "auto_reaped": <int>,
  "events_with_diagnostics": <int>,
  "explicit_reaped": <int>,
  "final_alive_count": <int>,
  "forks_rejected": <int>,
  "forks_succeeded": <int>,
  "killed_by_signal": <int>,
  "max_concurrent_processes": <int>,
  "orphans_reparented": <int>,
  "total_events": <int>,
  "users_at_end": [<int>, ...],
  "zombies_at_end": <int>
}
```

- `auto_reaped` counts every reap with `trigger == "init_reap"`.
- `events_with_diagnostics` counts the number of seq values that emitted at
  least one diagnostic (i.e. the length of `process_diagnostics.events`).
- `explicit_reaped` counts every reap with `trigger == "wait"`.
- `final_alive_count` counts processes whose final `state` is `"RUNNING"`.
- `forks_succeeded` counts every successful fork; `forks_rejected` counts
  forks that emitted `E_INVALID_PARENT` or `E_PID_REUSED`.
- `killed_by_signal` counts every kill that emitted `W_KILLED_BY_SIGNAL`
  (i.e. SIGTERM / SIGKILL / SIGINT against a RUNNING target).
- `max_concurrent_processes` is the largest count of processes in
  `{RUNNING, ZOMBIE}` reached at any point during the trace, including the
  initial state at the start.
- `orphans_reparented` counts every `W_ORPHANED` diagnostic emitted (so
  this counts orphans in BOTH `orphan_handling` modes; the policy gates
  whether the ppid actually changes, but the diagnostic fires either way).
- `total_events` is the count of `events.json[*]` (post `seq` validation).
- `users_at_end` is the sorted-ascending list of distinct integer `uid`
  values of processes whose final `state` is `"RUNNING"` (so an
  `EXITED`-only uid does not appear).
- `zombies_at_end` counts processes whose final `state` is `"ZOMBIE"`.
