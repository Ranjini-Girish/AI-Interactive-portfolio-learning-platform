# Reaping and Orphan Rules

When a process transitions from `RUNNING` to `ZOMBIE` (via `exit` or via
`kill` with a state-mutating signal), the simulator runs the same
orphan-and-reap pipeline. The pipeline has three phases that ALWAYS execute
in this order; later phases see the table mutations from earlier phases.

## Phase 1: orphan-reparent

Iterate every other process in the table (in pid-ascending order) whose
current `ppid` equals the just-died process's pid. For every such child:

- Emit `W_ORPHANED` with `pid` set to the child pid.
- Under `policy.orphan_handling == "reparent_to_init"`, rewrite the child's
  `ppid` to `policy.init_pid`. When `policy.track_lineage` is true, add a
  `"reparent_init"` edge `init_pid -> child_pid` to `lineage_graph.edges`
  (deduplicated).
- Under `policy.orphan_handling == "leave_orphaned"`, do NOT rewrite the
  `ppid`; the child's `ppid` continues to point at the (now-zombie or
  shortly-EXITED) parent. `W_ORPHANED` still fires but no
  `"reparent_init"` lineage edge is added.

Both `RUNNING` and `ZOMBIE` children are reparented. `EXITED` children are
not (they are already reaped and the table no longer treats them as
attached). The order in which `W_ORPHANED` diagnostics for multiple orphans
are emitted is pid-ascending; within a single seq the diagnostic-sort then
re-orders by `(severity_rank, code, pid)` (see `output_format.md`).

## Phase 2: implicit init-reap of reparented zombie children

If `policy.implicit_init_reap == true` AND
`policy.orphan_handling == "reparent_to_init"`, every reparented child
whose state is `ZOMBIE` AND whose new `ppid` equals `init_pid` is reaped:

- Transition the child to `EXITED`.
- Append a `reap_log` entry with `parent_pid == init_pid`,
  `pid == child_pid`, `seq` and `tick` from the triggering event, and
  `trigger == "init_reap"`.
- Emit `N_AUTO_REAPED` with `pid` set to the reaped child.

Process the reparented zombie children in pid-ascending order; each
auto-reap appends its own `reap_log` entry and `N_AUTO_REAPED` diagnostic.

A reparented child that is `RUNNING` is NOT touched by phase 2 (only
zombies are reaped). When `implicit_init_reap == false` OR
`orphan_handling == "leave_orphaned"`, phase 2 is skipped entirely.

## Phase 3: implicit init-reap of the just-died process itself

If `policy.implicit_init_reap == true` AND the just-died process's
*current* `ppid` equals `init_pid` (this includes the case where the
just-died process was a direct child of init from the start, AND the case
where the just-died process had previously been reparented to init), reap
it:

- Transition the just-died process to `EXITED`.
- Append a `reap_log` entry with `parent_pid == init_pid`,
  `pid == <just-died>`, `seq` and `tick` from the triggering event, and
  `trigger == "init_reap"`.
- Emit `N_AUTO_REAPED` with `pid` set to the just-died process.

Phase 3 fires AFTER phase 2 has run, so an orphan reparent from phase 1
that turns the just-died process's grandchild into init's child can only be
reaped by phase 2 (not phase 3). Conversely, if the just-died process's
ppid was already init at event time, phase 3 reaps it after its own
children have been processed in phase 1 and (where applicable) phase 2.

## Explicit `wait` reap

A successful `wait` event reaps exactly one zombie child of the issuer (see
`events.md` for the priority order over the four wait-failure conditions).
A successful wait emits `N_REAPED` with `pid` set to the reaped child and
appends a `reap_log` entry whose `trigger` is `"wait"` (not `"init_reap"`).

A `wait` whose precondition fails NEVER reaps anything and NEVER appends to
`reap_log`; it only emits its diagnostic and continues.

## End-of-trace zombie leak

After every event has been processed, every process whose state is still
`ZOMBIE` is "leaked": for each such process, emit `W_ZOMBIE_LEAK` with
`pid` set to the leaked pid AND `seq` set to the leaked process's exit
event seq (the seq of the `exit` or `kill` event that turned it into a
zombie). Use ONLY this seq value: not the last-event seq, not a sentinel
like `-1` or `INT64_MAX`, not the seq of a `wait` that failed to reap it.

If multiple processes leak with the same exit seq, all their
`W_ZOMBIE_LEAK` diagnostics share that seq, sorted within the event by
`(severity_rank, code, pid)` per `output_format.md`.

The processes that leak stay at state `ZOMBIE` in `process_state.json` (the
end-of-trace diagnostic is decorative; it does NOT change state).
