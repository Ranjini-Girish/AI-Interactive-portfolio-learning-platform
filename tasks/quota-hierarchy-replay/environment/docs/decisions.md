# Decision Catalogue

Every event produces **exactly one** decision entry in
`allocation_decisions.json`. The `decision` and `reason` fields are
drawn from closed sets and are restricted to six parallel pairings.

| `decision` | `reason`                    | When                                                                                          | `blocking_namespace`                              | `resources_granted`                       |
| ---------- | --------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------- | ----------------------------------------- |
| `admitted` | `under_limits`              | allocate that fits within `self.limits` and every ancestor's limits                          | `null`                                            | the event's `resources`                   |
| `rejected` | `unknown_namespace`         | allocate against a namespace not in `namespaces.json`                                          | `null`                                            | `{cpu:0, memory:0, storage:0}`            |
| `rejected` | `limit_exceeded`            | allocate that would push some ancestor's `used_subtree` past its `limits`                    | the deepest blocking ancestor (closest to target) | `{cpu:0, memory:0, storage:0}`            |
| `rejected` | `release_underflow`         | release whose amounts exceed the target namespace's `used_own` on any resource                | the target namespace                              | `{cpu:0, memory:0, storage:0}`            |
| `ignored` | `release_unknown_ignored`   | release against an unknown namespace when `config.release_unknown_action == "ignore"`        | `null`                                            | `{cpu:0, memory:0, storage:0}`            |
| `rejected` | `release_unknown_rejected`  | release against an unknown namespace when `config.release_unknown_action == "reject"`        | `null`                                            | `{cpu:0, memory:0, storage:0}`            |

## Decision precedence

For each event in `allocations.events`:

1. Unknown namespace + `op == "allocate"` → `rejected /
   unknown_namespace`.
2. Unknown namespace + `op == "release"` → dispatch on
   `config.release_unknown_action`.
3. `op == "allocate"`: walk ancestors from `self` up to root; pick the
   **deepest** ancestor whose `used_subtree + resources` would exceed
   its `limits` on any resource. If any, reject with
   `limit_exceeded`. Otherwise admit.
4. `op == "release"`: if any resource in the event exceeds the target's
   current `used_own`, reject with `release_underflow`. Otherwise
   subtract from the target's `used_own` and from every ancestor's
   `used_subtree`.

`(decision, reason)` pairs outside this table are forbidden and
constitute a verifier violation.

## `blocking_namespace` semantics

For `limit_exceeded`: the deepest ancestor in the chain from `self` to
root whose post-admit subtree usage would exceed its own limits. When
`self` itself would violate its own limits, the blocking namespace is
`self`.

For `release_underflow`: the namespace that the release targeted (the
event's `namespace`), since that's the level at which the underflow
would occur (`used_own` going negative).
