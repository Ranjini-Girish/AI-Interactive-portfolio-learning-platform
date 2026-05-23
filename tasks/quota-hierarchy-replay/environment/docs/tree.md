# Namespace Tree Semantics

## Structure

`namespaces.json` declares a rooted tree:

```json
{
  "namespaces": [
    {"name": "root",   "parent": null,   "limits": {"cpu": 100, "memory": 1024, "storage": 10000}},
    {"name": "team_a", "parent": "root", "limits": {"cpu": 60,  "memory": 512,  "storage": 5000}},
    {"name": "team_b", "parent": "root", "limits": {"cpu": 40,  "memory": 256,  "storage": 4000}},
    {"name": "team_a_alpha", "parent": "team_a", "limits": {"cpu": 30, "memory": 256, "storage": 2000}}
  ]
}
```

Validation rules:

* Every `name` is unique across the array.
* Exactly one node has `parent == null` (the root).
* Every non-root `parent` references some other namespace by `name`.
* The result is acyclic.
* Every `limits.cpu` / `limits.memory` / `limits.storage` is a
  **non-negative integer**.

A violation of any of the above MUST be rejected as malformed input
(non-zero exit, no output written).

## Limits and usage

Each namespace maintains two counters per resource:

* `used_own`: net amount allocated **directly** to that namespace
  (admitted allocates minus admitted releases targeting that name).
* `used_subtree`: roll-up of `used_own` across the namespace and all
  descendants.

For an admit decision to apply to namespace `N` with resources `R`:

* For every ancestor `A` of `N` (with `A` ranging from `N` up to the
  root, inclusive), the post-admit value `A.used_subtree + R` MUST not
  exceed `A.limits` on **any** resource.

When the constraint is violated, the engine identifies the **deepest**
blocking ancestor (i.e. the one closest to `N` in the tree) and uses it
as `blocking_namespace`. When `N` itself fails the check, `N` is the
blocking namespace.

`headroom[r]` per namespace is defined as `limits[r] - used_subtree[r]`.
After the replay it MAY be zero (fully utilized) but cannot be
negative on any admitted path. If the replay produces a negative
`headroom`, the engine has misaccounted and the verifier WILL flag it.
