# Output Format

Five files MUST be written under `argv[2]`, each a regular file (no
symlinks), and nothing else.

## Canonical JSON

Every output file is the byte-for-byte result of:

```python
json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
```

UTF-8 wire bytes that are ASCII-only at the file-byte level, two-space
indent, keys sorted lexicographically at every depth, single trailing
newline.

## `allocation_decisions.json`

```json
{
  "decisions": [
    {
      "event_id": "e_0001",
      "ts_unix_ms": 100,
      "namespace": "team_a",
      "op": "allocate",
      "decision": "admitted",
      "reason": "under_limits",
      "blocking_namespace": null,
      "resources_granted": {"cpu": 10, "memory": 64, "storage": 100}
    }
  ]
}
```

Sorted by `event_id` ascending. Exactly one entry per input event.

## `namespace_usage.json`

```json
{
  "namespaces": [
    {
      "name": "root",
      "limits": {"cpu": 100, "memory": 1024, "storage": 10000},
      "used_own": {"cpu": 0, "memory": 0, "storage": 0},
      "used_subtree": {"cpu": 75, "memory": 600, "storage": 6500},
      "headroom": {"cpu": 25, "memory": 424, "storage": 3500},
      "descendant_count": 3
    }
  ]
}
```

Sorted by `name`. One entry per namespace in `namespaces.json`.

* `used_own` is the net of admitted allocates minus admitted releases
  targeting that namespace directly.
* `used_subtree` rolls `used_own` across the namespace and every
  descendant.
* `headroom[r] = limits[r] - used_subtree[r]` (cannot be negative on any
  consistent replay).
* `descendant_count` excludes self.

## `rollup_tree.json`

```json
{
  "tree": [
    {
      "name": "root",
      "parent": null,
      "depth": 0,
      "children": ["team_a", "team_b"],
      "used_subtree": {"cpu": 75, "memory": 600, "storage": 6500}
    }
  ]
}
```

Depth-first pre-order traversal starting at the root; child order at
every node is alphabetical by `name`. `parent` is `null` for the root,
`depth` is 0 for the root and increments by 1 at every level.

## `violations.json`

```json
{
  "violations": [
    {
      "event_id": "e_0042",
      "ts_unix_ms": 4200,
      "namespace": "team_a",
      "op": "allocate",
      "decision": "rejected",
      "reason": "limit_exceeded",
      "blocking_namespace": "team_a",
      "resources_granted": {"cpu": 0, "memory": 0, "storage": 0},
      "attempted_resources": {"cpu": 200, "memory": 0, "storage": 0}
    }
  ]
}
```

Sorted by `event_id`. One entry per event with `decision == "rejected"`.
`attempted_resources` is the `resources` field from the original event
(distinct from `resources_granted`, which is always all-zeros on
rejection).

## `summary.json`

```json
{
  "admitted_events": 28,
  "hottest_namespace": "root",
  "ignored_events": 1,
  "limit_exceeded_rejects": 3,
  "rejected_events": 5,
  "release_underflow_rejects": 1,
  "total_events": 34,
  "total_namespaces": 7,
  "unknown_namespace_rejects": 1
}
```

`hottest_namespace` is the namespace with the largest
`used_subtree.cpu + used_subtree.memory + used_subtree.storage` after
the replay; ties are broken alphabetically. If every namespace has zero
subtree usage, `hottest_namespace` is `null`.
