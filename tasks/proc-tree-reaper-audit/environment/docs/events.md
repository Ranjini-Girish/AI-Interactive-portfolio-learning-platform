# Event Semantics

Every event has the same flat shape:

```
{
  "seq": <int>,
  "tick": <int>,
  "op": "fork" | "exit" | "wait" | "kill" | "exec",
  "pid": <int>,                  // the issuing pid (always non-null)
  "parent_pid": <int> | null,    // fork only; the parent of the new pid
  "target_pid": <int> | null,    // wait/kill only; the target pid
  "exit_code": <int> | null,     // exit only
  "signal": <str> | null,        // kill only; closed set
  "cmdline": <str> | null        // fork/exec only
}
```

An event can only emit ONE error code per event. The catalogue below lists
the documented priority order; the simulator short-circuits on the first
match.

## `fork`

A new process is created with the supplied `pid`, parent set to
`parent_pid`, `uid` inherited from `parent_pid`, `start_tick` set to the
event `tick`, and `cmdline` either the event's `cmdline` (if non-null) or
the parent's current `cmdline` (if `cmdline` is null).

Priority-ordered preconditions:

1. `parent_pid` must name a process whose current `state` is `"RUNNING"`.
   A non-existent `parent_pid` or a `parent_pid` whose state is `ZOMBIE` or
   `EXITED` emits `E_INVALID_PARENT` with `pid` set to the bad
   `parent_pid` and the event is skipped.
2. `pid` must not already appear in the `seen_pids` set (the union of every
   initial pid and every pid named by a successful prior `fork`). Reuse of
   such a pid emits `E_PID_REUSED` with `pid` set to the reused value.

If both preconditions hold, the new process enters `RUNNING` state. When
`policy.track_lineage` is true, a `"fork"` edge `parent_pid -> pid` is
added to `lineage_graph.edges` (deduplicated; identical fork edges from a
forge that succeeds twice for distinct pids both appear).

## `exit`

The issuing `pid` voluntarily terminates with an integer `exit_code`. The
event's `target_pid`, `signal`, and `parent_pid` fields must be `null` (the
schema enforces this; see `schemas/events_input.schema.json`).

Priority-ordered preconditions:

1. `pid` must name a process that exists in the table.
   A non-existent `pid` emits `E_INVALID_TARGET` with `pid` set to the bad
   value and the event is skipped.
2. The process must be in `RUNNING` state. A `ZOMBIE` or `EXITED` process
   emits `E_DOUBLE_EXIT` with `pid` set to the dead pid and the event is
   skipped.

If both preconditions hold, the process transitions to `ZOMBIE`,
`exit_tick` becomes the event `tick`, `exit_code` becomes the event's
`exit_code`, and `exit_signal` stays `null`. Then the orphan-and-reap
pipeline runs (see `reaping.md`) on the just-died process: every child of
this pid is reparented if `policy.orphan_handling == "reparent_to_init"`,
W_ORPHANED is emitted per orphaned child (under both
`orphan_handling` modes; the only difference is whether the child's `ppid`
gets rewritten to `init_pid`), and any reparented zombie child whose new
`ppid` equals `init_pid` is auto-reaped if
`policy.implicit_init_reap == true`. Finally, if the just-died process's
own `ppid` equals `init_pid` AND `implicit_init_reap == true`, IT is
auto-reaped and transitions to `EXITED` immediately, with one
`N_AUTO_REAPED` diagnostic and a `reap_log` entry whose
`trigger == "init_reap"`.

## `wait`

The issuing `pid` waits on a child to reap a zombie. `target_pid` is the
specific child to wait on; if `target_pid` is `null`, the simulator picks
the lex-smallest pid satisfying `ppid == issuer && state == ZOMBIE`.

Priority-ordered preconditions:

1. The issuing `pid` must name a process whose state is `RUNNING`. Otherwise
   `E_INVALID_TARGET` with `pid` set to the bad issuer.
2. If `target_pid` is non-null, it must name a process in the table.
   Otherwise `E_INVALID_TARGET` with `pid` set to `target_pid`.
3. If `target_pid` is non-null, its `ppid` must equal the issuing `pid`.
   Otherwise `E_NOT_CHILD` with `pid` set to `target_pid`.
4. The resolved child (either `target_pid` or the lex-smallest zombie child
   under `target_pid == null`) must be in `ZOMBIE` state.
   - If `target_pid` is non-null and the child is `RUNNING`,
     `E_NOT_ZOMBIE` is emitted under
     `policy.wait_on_living_child == "diagnostic"`, and the event is a
     silent no-op under `wait_on_living_child == "noop"`.
   - If `target_pid` is non-null and the child is `EXITED` (already reaped),
     emit `E_INVALID_TARGET` with `pid` set to `target_pid`.
   - If `target_pid` is `null` and no `ZOMBIE` child of the issuer exists,
     emit `E_NOT_ZOMBIE` with `pid` set to `null`.

If all preconditions hold and the resolved child is `ZOMBIE`, the child
transitions to `EXITED`, one `N_REAPED` is emitted with `pid` set to the
reaped child, and a `reap_log` entry is appended with
`parent_pid` set to the issuer, `pid` set to the reaped child, `seq`/`tick`
from the event, and `trigger == "wait"`.

## `kill`

The issuing `pid` sends `signal` to `target_pid`. The closed set of signals
is exactly `{"SIGTERM", "SIGKILL", "SIGINT", "SIGCHLD"}`; any other signal
in the events file is a malformed input.

Priority-ordered preconditions:

1. The issuing `pid` must name a process whose state is `RUNNING`. Otherwise
   `E_INVALID_TARGET` with `pid` set to the bad issuer.
2. `target_pid` must name a process whose state is `RUNNING`. Otherwise
   `E_INVALID_TARGET` with `pid` set to the bad `target_pid`.

If both preconditions hold:

- `signal == "SIGCHLD"` is a silent no-op (no diagnostic, no state change).
- `signal in {"SIGTERM", "SIGKILL", "SIGINT"}` transitions `target_pid` to
  `ZOMBIE` with `exit_tick` set to the event `tick`, `exit_code` set to
  `null`, and `exit_signal` set to the `signal` string. Emit
  `W_KILLED_BY_SIGNAL` with `pid` set to `target_pid`, then run the same
  orphan-and-reap pipeline described under `exit` against the killed
  target.

The kill issuer never transitions; it just emits the signal.

## `exec`

The issuing `pid` replaces its `cmdline` in place. The event's
`parent_pid`, `target_pid`, `exit_code`, and `signal` fields must be `null`.

Priority-ordered preconditions:

1. `pid` must name a process whose state is `RUNNING`. Otherwise
   `E_INVALID_TARGET` with `pid` set to the bad issuer.

If the precondition holds, set `cmdline` to the event's `cmdline`. No
diagnostic is emitted on success; `exec` is a "silent" event. `tick` /
`start_tick` are NOT updated by `exec`.
