# Diagnostic Codes

`process_diagnostics.json` carries one entry per event that emitted at
least one diagnostic. Events with zero diagnostics are NOT listed - the
array is sparse, sorted by `seq` ascending. Within an event the
`diagnostics` list is sorted by `(severity_rank, code, pid)` where `pid`
sorted as integer with `null` sorting BEFORE every integer value. Severity
ranks: `error` = 0, `warning` = 1, `note` = 2.

The closed code set is exactly:

| Code                     | Severity | `pid`                                  | Fired by                                       |
|--------------------------|----------|----------------------------------------|------------------------------------------------|
| `E_INVALID_PARENT`       | error    | the bad `parent_pid`                   | `fork` whose `parent_pid` is missing or not RUNNING |
| `E_PID_REUSED`           | error    | the reused `pid`                       | `fork` whose `pid` was already observed       |
| `E_INVALID_TARGET`       | error    | the bad `pid` or `target_pid`          | `exit`, `wait`, `kill`, `exec` whose addressed pid is missing OR not RUNNING (issuer or target) |
| `E_DOUBLE_EXIT`          | error    | the dead `pid`                         | `exit` whose `pid` is already ZOMBIE or EXITED |
| `E_NOT_CHILD`            | error    | the unrelated `target_pid`             | `wait` whose `target_pid` exists but is not the issuer's child |
| `E_NOT_ZOMBIE`           | error    | the still-RUNNING `target_pid`, or `null` for wait-any with no zombies | `wait` |
| `W_KILLED_BY_SIGNAL`     | warning  | the killed `target_pid`                | `kill` with SIGTERM/SIGKILL/SIGINT             |
| `W_ORPHANED`             | warning  | each orphaned child pid                | `exit` or `kill` whose victim has children     |
| `W_ZOMBIE_LEAK`          | warning  | each leaked zombie's `pid`             | end-of-trace, attached to the zombie's exit seq |
| `N_AUTO_REAPED`          | note     | the reaped pid                         | `exit` or `kill` whose victim is auto-reaped under `policy.implicit_init_reap` |
| `N_REAPED`               | note     | the reaped pid                         | a successful `wait`                            |

There are exactly eleven legal codes. Any other code or severity is a bug.

## Notes on the priority order

A single failing event emits at most ONE error code. The
priority order is documented per-op in `events.md` and recapped here:

- **`fork`**: `E_INVALID_PARENT` before `E_PID_REUSED` (so a fork that
  picks both a missing parent AND a reused pid emits only
  `E_INVALID_PARENT`).
- **`exit`**: `E_INVALID_TARGET` before `E_DOUBLE_EXIT`.
- **`wait`**: `E_INVALID_TARGET` (issuer or target) before `E_NOT_CHILD`
  before `E_NOT_ZOMBIE`. The `wait_on_living_child` policy gates whether
  `E_NOT_ZOMBIE` fires for a still-RUNNING child.
- **`kill`**: `E_INVALID_TARGET` (issuer or target) before any
  signal-specific handling. The signal field is validated as part of the
  malformed-input check, not as a diagnostic.
- **`exec`**: only `E_INVALID_TARGET` (issuer must be RUNNING).

When an event emits warnings or notes (e.g. `W_KILLED_BY_SIGNAL` and
`W_ORPHANED` and `N_AUTO_REAPED` all on the same kill seq), they all appear
in the same `events[*].diagnostics` array, sorted by
`(severity_rank, code, pid)`.

## End-of-trace `W_ZOMBIE_LEAK`

`W_ZOMBIE_LEAK` is special because it does not fire when an event is being
handled - it fires after every event has been processed. Each leaked zombie
attaches its `W_ZOMBIE_LEAK` diagnostic to the seq of its OWN exit event
(the `exit` or `kill` that turned it into a zombie). If two zombies leak
with the same exit seq, both `W_ZOMBIE_LEAK` diagnostics are placed under
that seq's diagnostic list. If the same seq already had other diagnostics
(say `W_ORPHANED` for that exit's children), `W_ZOMBIE_LEAK` joins the
existing list and is sorted in.

A zombie that gets reaped (by `wait` or by `init_reap`) before trace end
does NOT emit `W_ZOMBIE_LEAK`.
