# Event Semantics

Each event has a `seq`, an `op`, and a subset of the optional fields `id`,
`parent_id`, `cpu_quota_ms`, `mem_quota_kb`, `io_quota_iops`, `task_id`,
`amount`, and `target_parent_id` (filled with `null` when unused). Unused
fields MUST be present and `null` -- the input file always emits the same
key set per event.

## `create`

Required: `id`, `parent_id` (string id or `null` for a root),
`cpu_quota_ms`, `mem_quota_kb`, `io_quota_iops`. Adds a fresh cgroup.
Failure modes (in priority order):

1. `id` already exists -> emit `E_DUPLICATE_ID`, no state change.
2. `parent_id` is non-null and does not name an existing cgroup -> emit
   `E_PARENT_NOT_FOUND`, no state change.
3. `mem_quota_kb < policy.min_quota_kb` -> emit `E_BELOW_MIN_QUOTA`, no state
   change.
4. Otherwise add the cgroup. Initial usage counters and peaks are zero, the
   `tasks` set is empty.

## `delete`

Required: `id`. Removes a cgroup. The cgroup must be a leaf -- it must have
no child cgroups -- otherwise emit `E_HAS_CHILDREN` and skip. If the id does
not exist, emit `E_CGROUP_NOT_FOUND`.

If the cgroup has no tasks, the delete proceeds quietly.

If the cgroup has tasks, the next branch depends on `policy.delete_action`:

- `"reject_if_tasks"`: emit `E_HAS_TASKS_REJECT`, no state change.
- `"reparent_to_parent"`: every task currently attached to the cgroup is
  moved to the cgroup's parent (which is the root forest's "outside" --
  i.e. tasks become detached -- when the deleted cgroup was a root).
  Specifically: when the deleted cgroup has a non-null `parent_id`, every
  task is reattached to that parent and one `W_REPARENTED` warning per
  reparented task is emitted (carrying the `task_id` of the reparented task
  and the destination parent id). When the deleted cgroup is a root, every
  task is silently detached (no `W_REPARENTED` emitted in that case -- the
  diagnostic is specifically about reparenting to a real new home, not
  about losing a home altogether). The cgroup is then removed.

When `delete` succeeds against a cgroup whose accumulated `cpu_used_ms`,
`mem_used_kb`, or `io_used_iops` were non-zero, the simulator simply
discards those counters along with the cgroup; no diagnostic is emitted.

`delete` does NOT contribute lineage edges.

## `attach_task`

Required: `id` (the cgroup), `task_id`. Attaches a task to a cgroup.
Failure modes (in priority order):

1. `id` does not exist -> `E_CGROUP_NOT_FOUND`.
2. `task_id` is already attached to ANY cgroup (including this one) ->
   `E_TASK_ALREADY_ATTACHED`, no state change.

Otherwise the task is added to the cgroup's `tasks` set.

## `detach_task`

Required: `id`, `task_id`. Detaches a task from a cgroup. Failure modes
(in priority order):

1. `id` does not exist -> `E_CGROUP_NOT_FOUND`.
2. `task_id` is not attached to this specific cgroup -> `E_TASK_NOT_FOUND`
   (regardless of whether the task is attached elsewhere).

Otherwise the task is removed from the cgroup's `tasks` set.

## `consume_cpu` / `consume_mem` / `consume_io`

Required: `id`, `amount` (a non-negative integer). Increments the matching
`*_used_*` counter. If the counter would exceed the cgroup's matching
`*_quota_*`, the next branch depends on `policy.over_quota_action`:

- `"reject"`: emit `E_OVER_QUOTA`, no state change.
- `"throttle"`: increment the counter only by the headroom remaining
  (so the counter ends up equal to the quota), and emit `W_THROTTLED`
  carrying the integer `amount_dropped` (the part of `amount` that was
  refused). When the counter is already at quota, throttle drops the entire
  amount; when there is some headroom but less than `amount`, throttle
  drops the excess and accepts the headroom.

If `amount == 0`, the consume is a silent no-op (no diagnostic, no quota
check). If `id` does not exist, emit `E_CGROUP_NOT_FOUND` regardless of
`amount`.

For `consume_cpu` and `consume_mem` the simulator updates the corresponding
peak counter on every successful increment (full or throttled-partial),
right after the increment: `peak = max(peak, used)`.

`consume_io` does NOT track a peak.

## `release_cpu` / `release_mem`

Required: `id`, `amount` (non-negative integer). Decrements the matching
`*_used_*` counter, but never below zero. If the requested release exceeds
the current used value, the counter is set to zero and a `W_RELEASE_UNDERFLOW`
warning is emitted carrying the `amount_clamped` (the integer by which the
release exceeded the used value).

If `amount == 0`, the release is a silent no-op. If `id` does not exist,
emit `E_CGROUP_NOT_FOUND`.

`release_cpu` and `release_mem` do NOT change the peak counters -- peaks
only ever go up.

There is no `release_io` -- IOPS in this simulator are a rate-style counter
that resets only via `update_quota`, never via release.

## `update_quota`

Required: `id`, `cpu_quota_ms`, `mem_quota_kb`, `io_quota_iops`. Replaces
the named cgroup's three quotas in one shot. Failure modes (in priority
order):

1. `id` does not exist -> `E_CGROUP_NOT_FOUND`.
2. `mem_quota_kb < policy.min_quota_kb` -> `E_BELOW_MIN_QUOTA`, no state
   change.

The new quotas may be lower than the current `*_used_*` counters; this is
allowed and does NOT retroactively emit `E_OVER_QUOTA` or `W_THROTTLED`
(the diagnostic is bound to the consume event, not to the quota drop).

`update_quota` never touches the peak counters.

## `move_subtree`

Required: `id`, `target_parent_id` (string id or `null` to move to root).
Moves a cgroup (taking its descendants with it) under a new parent.
Failure modes (in priority order):

1. `id` does not exist -> `E_CGROUP_NOT_FOUND`.
2. `target_parent_id` is non-null and does not name an existing cgroup ->
   `E_PARENT_NOT_FOUND`.
3. `target_parent_id` equals `id` itself, or is currently a descendant of
   `id` -> `E_CYCLE_REJECTED`.

When successful the cgroup's `parent_id` is set to `target_parent_id`.
The descendants are NOT relinked individually -- only the moved cgroup's
`parent_id` changes; its children continue to point at it.

`move_subtree` is the ONLY event that contributes lineage edges; see
`lineage.md`.
