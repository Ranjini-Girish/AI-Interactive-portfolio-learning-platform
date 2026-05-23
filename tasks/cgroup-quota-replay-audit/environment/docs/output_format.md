# Output Format

Five files in `/app/output/`. Every file is canonical JSON: UTF-8,
ASCII-only escaping (`ensure_ascii=True`), two-space indent, object keys
lex-sorted at every depth, single trailing newline. Integer values stay
integers (do not emit them as JSON numbers with a decimal point); booleans
stay booleans; the empty list is `[]` not `null`.

## `cgroup_state.json`

```
{
  "cgroups": [
    {
      "cpu_quota_ms":  <int>,
      "cpu_used_ms":   <int>,
      "id":            <str>,
      "io_quota_iops": <int>,
      "io_used_iops":  <int>,
      "mem_quota_kb":  <int>,
      "mem_used_kb":   <int>,
      "parent_id":     <str|null>,
      "peak_cpu_ms":   <int>,
      "peak_mem_kb":   <int>,
      "tasks":         [<task_id>, ...]
    },
    ...
  ]
}
```

`cgroups` is sorted ASCII ascending by `id`. `tasks` inside each cgroup is
sorted ASCII ascending. Includes every cgroup currently present at trace
end (i.e. not deleted). Deleted cgroups do NOT appear here -- but their
ids may still appear in `lineage_graph.nodes`.

## `quota_violation_log.json`

```
{
  "violations": [
    {
      "amount":         <int>,
      "amount_dropped": <int>,
      "cgroup_id":      <str>,
      "code":           "E_OVER_QUOTA" | "W_THROTTLED",
      "resource":       "cpu" | "mem" | "io",
      "seq":            <int>
    },
    ...
  ]
}
```

Chronological order, no sorting. `seq` repeats are impossible (one consume
event produces at most one violation entry).

## `task_assignments.json`

```
{
  "tasks": [
    { "cgroup_id": <str>, "task_id": <str> },
    ...
  ]
}
```

Sorted ASCII ascending by `task_id`. Carries every task that is currently
attached to some cgroup at trace end (a task that was attached and then
detached, OR a task that was attached and then orphaned by a delete on a
root cgroup under `delete_action == "reparent_to_parent"`, does NOT appear).

## `lineage_graph.json`

```
{
  "cycles": [ [<id>, ...], ... ],
  "edges":  [ { "from": <str>, "to": <str> }, ... ],
  "nodes":  [ { "id": <str>, "in_degree": <int>, "out_degree": <int> }, ... ]
}
```

See `lineage.md` for what fills these. When `policy.track_lineage` is false
all three arrays are `[]`.

`edges` sorted by `(from, to)`. `nodes` sorted by `id` ASCII ascending.
`cycles` lists multi-vertex SCCs sorted by lex-smallest member; each cycle
is a sorted-ASCII list of the cycle's member ids.

## `summary.json`

```
{
  "creates_rejected":          <int>,   // "create" ops that emitted any error diagnostic
  "creates_succeeded":         <int>,   // "create" ops that ended up adding the cgroup
  "deletes_succeeded":         <int>,   // "delete" ops that actually removed a cgroup
  "final_cgroup_count":        <int>,   // length of cgroup_state.cgroups
  "final_task_count":          <int>,   // length of task_assignments.tasks
  "hot_cgroups":               [        // sorted by (-violation_count, id)
    { "id": <str>, "violation_count": <int> },
    ...
  ],
  "moves_succeeded":           <int>,   // successful "move_subtree" ops
  "rejected_consumes":         <int>,   // # of E_OVER_QUOTA entries in quota_violation_log
  "throttled_consumes":        <int>,   // # of W_THROTTLED entries in quota_violation_log
  "total_events":              <int>,   // events_in.length
  "total_violations":          <int>    // length of quota_violation_log.violations
}
```

`creates_succeeded + creates_rejected` equals the total `create` event count.
`rejected_consumes + throttled_consumes == total_violations`.

`hot_cgroups` includes EVERY cgroup id that appears at least once in
`quota_violation_log.violations` (regardless of whether the cgroup still
exists at trace end -- a cgroup that was deleted after racking up
violations still appears in `hot_cgroups`). The list is sorted with the
most-violating cgroups FIRST (`-violation_count`), with ASCII-ascending
`id` as the tiebreaker on equal counts. Cgroups with zero violations are
NOT in `hot_cgroups`.
