# Diagnostic Codes

`quota_violation_log.json` is NOT the global diagnostic stream. It carries
a chronological list of every `consume_*` event that hit `E_OVER_QUOTA` or
`W_THROTTLED` (the rest of the diagnostics live only in the rejection /
warning text emitted to stderr by your implementation; the verifier does
NOT examine stderr). The diagnostics that DO appear in
`quota_violation_log.json` are the closed two-code subset documented at
the bottom of this file.

There are exactly FOURTEEN legal diagnostic codes the simulator may
emit across the whole run, and only the `E_OVER_QUOTA` / `W_THROTTLED`
subset is allowed to surface in `quota_violation_log.json` (the
verifier checks that no other code does). Severity ranks: `error` = 0,
`warning` = 1, `note` = 2.

| Code                          | Severity | Fired by                                                   |
|-------------------------------|----------|------------------------------------------------------------|
| `E_DUPLICATE_ID`              | error    | `create`                                                    |
| `E_PARENT_NOT_FOUND`          | error    | `create`, `move_subtree`                                    |
| `E_CGROUP_NOT_FOUND`          | error    | `delete`, `attach_task`, `detach_task`, `consume_*`, `release_*`, `update_quota`, `move_subtree` |
| `E_TASK_NOT_FOUND`            | error    | `detach_task`                                               |
| `E_TASK_ALREADY_ATTACHED`     | error    | `attach_task`                                               |
| `E_BELOW_MIN_QUOTA`           | error    | `create`, `update_quota`                                    |
| `E_HAS_CHILDREN`              | error    | `delete`                                                    |
| `E_HAS_TASKS_REJECT`          | error    | `delete` under `delete_action == "reject_if_tasks"`         |
| `E_CYCLE_REJECTED`            | error    | `move_subtree` (target equals self or is a descendant)      |
| `E_QUOTA_SUM_EXCEEDS_PARENT`  | error    | `create`, `update_quota`, `move_subtree` under `quota_inheritance == "sum_children_capped"` |
| `E_OVER_QUOTA`                | error    | `consume_*` under `over_quota_action == "reject"`           |
| `W_THROTTLED`                 | warning  | `consume_*` under `over_quota_action == "throttle"`         |
| `W_REPARENTED`                | warning  | `delete` under `delete_action == "reparent_to_parent"` (one per task reparented) |
| `W_RELEASE_UNDERFLOW`         | warning  | `release_cpu`, `release_mem`                                |

## What `quota_violation_log.json` records

Only the consume-time diagnostics show up in
`quota_violation_log.json`. Concretely the log carries one entry per
`consume_*` event that emitted exactly one of:

- `E_OVER_QUOTA` (the consume was rejected wholesale).
- `W_THROTTLED` (the consume was partially accepted).

Each entry has these six fields:

```
{
  "amount":         <int>,   // the requested consume amount
  "amount_dropped": <int>,   // amount - actually-applied
  "cgroup_id":      <str>,   // bottleneck cgroup (E_OVER_QUOTA) or consume target (W_THROTTLED)
  "code":           "E_OVER_QUOTA" | "W_THROTTLED",
  "resource":       "cpu" | "mem" | "io",
  "seq":            <int>    // the consume event's seq
}
```

Records appear in chronological order across the whole trace (no
sorting). A consume that succeeds within quota produces no log entry.
A consume on a missing cgroup (which emits `E_CGROUP_NOT_FOUND`)
produces no log entry either -- only over-quota outcomes go in.

The other diagnostic codes (`E_DUPLICATE_ID`, `W_REPARENTED`, etc.) do
NOT appear in `quota_violation_log.json`; they affect state-machine
behaviour and `summary` counters but are not part of the persisted
diagnostic stream.
