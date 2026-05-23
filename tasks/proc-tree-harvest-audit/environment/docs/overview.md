# Process Tree Replay Overview

The simulator models a single-host POSIX-style process tree. Each process
carries an integer `pid` (unique across the whole trace, never reused after a
prior holder reaches `EXITED`), an integer `ppid` (its parent's `pid`, or `0`
for a root), an integer `uid`, a string `state` (one of `"RUNNING"`,
`"ZOMBIE"`, or `"EXITED"`), an integer `start_tick`, an optional integer
`exit_tick`, an optional integer `exit_code`, an optional string
`exit_signal`, and a string `cmdline`.

The initial state is `processes.json`. Every initial process has
`state == "RUNNING"`, `exit_tick == null`, `exit_code == null`, and
`exit_signal == null`. Initial pids are unique and form a valid forest under
the `ppid` relation (a `ppid` of `0` denotes a root, every other `ppid` must
reference another initial pid). The set of pids that ever appear in the
simulation is the union of the initial pids and every pid named by a
successful `fork` event. The closed set of state values is exactly
`{"RUNNING", "ZOMBIE", "EXITED"}`; the simulator never invents others.

`events.json` is a strictly ascending list of operations (`seq` 0..N-1,
dense) that mutate the tree. Events are processed in `seq` order, one at a
time. After every event the global invariant must hold:

- every `ppid` either equals `0` or names a pid that is `RUNNING`, `ZOMBIE`,
  or `EXITED` (i.e. has been observed),
- the lineage induced by `ppid` is a forest (no cycles),
- `EXITED` is a terminal state: a pid that was once `EXITED` never
  transitions back, and never gets re-introduced by a later `fork`,
- `ZOMBIE` processes carry exactly one of `exit_code` or `exit_signal` set
  (the other is `null`).

Diagnostic-emitting events do not change state - when an event fails its
preconditions, the simulator emits the documented diagnostic for that event
and moves on without touching the process table. The exception is `kill`
with a signal that mutates state (see `events.md`); even there, the rejection
branches (target not in alive set, signal unknown) emit a diagnostic and skip
the kill itself.

`tick` is a non-negative integer logical timestamp carried by every event.
Multiple events may share the same `tick`; ordering across the trace is
always by `seq`, never by `tick`. The simulator never advances tick on its
own - tick only changes when a new event with a larger tick arrives.

## Input validation contract

Before running the simulation, the binary must validate `processes.json`
upfront: every non-zero `ppid` in an initial process must reference another
`pid` present in the same `processes.json`. A violation is malformed input
and the binary must exit non-zero without producing any file under
`/app/output/`. Type-level conformance to `schemas/processes_input.schema.json`
is necessary but not sufficient - the schema cannot express this
cross-row referential constraint, so enforcing it is the binary's
responsibility.
