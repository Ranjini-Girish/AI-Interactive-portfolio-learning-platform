# Cgroup Replay Overview

The simulator models a Linux-cgroup-style hierarchy: a forest of cgroups, each
identified by an opaque string `id`, linked by a `parent_id` (the literal
`null` for a root), each carrying three integer quota limits and three
integer current-usage counters:

- `cpu_quota_ms`, `cpu_used_ms`
- `mem_quota_kb`, `mem_used_kb`
- `io_quota_iops`, `io_used_iops`

Plus a `tasks` set (string ids), and two non-decreasing peak counters
`peak_cpu_ms` and `peak_mem_kb` that track the maximum value `cpu_used_ms`
and `mem_used_kb` ever reached for that cgroup over the trace.

The initial state is `cgroups.json`. Cgroup ids are unique across the whole
trace -- once a cgroup's id has been deleted (and the simulator emits no
diagnostic preventing the delete), that id may not be reintroduced by a
later `create`.

`events.json` is a strictly ascending list of operations (`seq` 0..N-1,
dense) that mutate the hierarchy. Events are processed in `seq` order, one
at a time. After every event the global invariants must hold:

- `parent_id` of every cgroup either is `null` (root) or names an existing
  cgroup,
- the parent-child graph stays a forest (no cycles, no shared children),
- every task is attached to at most one cgroup,
- ids that currently appear in `cgroup_state` are unique.

Diagnostic-emitting events do not change state when the diagnostic is an
error (`E_*`) -- the simulator emits the error and moves on without touching
any cgroup. Warning- and note-severity diagnostics (`W_*`, `N_*`) do
accompany state changes (e.g. `W_THROTTLED` rides along a partial consume,
`W_REPARENTED` rides along a successful delete-with-reparent). The closed
diagnostic-code set is documented in `diagnostics.md`.
