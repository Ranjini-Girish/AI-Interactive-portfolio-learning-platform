# Quota Inheritance and Over-Quota Handling

`policy.quota_inheritance` controls how the quota check on a `consume_*`
relates a child's usage to its ancestors' quotas.

## `"independent"`

Every cgroup is checked only against its own quota: a `consume_cpu` on
cgroup `C` with `amount=A` succeeds when `C.cpu_used_ms + A <=
C.cpu_quota_ms`. Ancestors are not consulted; they do not get their
`cpu_used_ms` bumped by descendants' consumption.

## `"strict"`

A `consume_*` on cgroup `C` is checked against `C` AND every ancestor of
`C` (the chain `C, parent(C), parent(parent(C)), ..., root`). The consume
succeeds only when *every* cgroup in the chain has enough headroom to
absorb `amount`. When the chain succeeds, the counter is incremented on
`C` only -- ancestors' `*_used_*` counters are NOT bumped (the spec
mirrors the way Linux's tracking-only "no-op" controllers behave).

Under `over_quota_action == "reject"`, the violating ancestor's id is
recorded as the `cgroup_id` of the `E_OVER_QUOTA` entry (not necessarily
`C`). When the chain has multiple ancestors that would all be over quota,
the diagnostic names the ancestor closest to `C` -- i.e. the first cgroup
walking from `C` upward whose quota would be exceeded.

Under `over_quota_action == "throttle"`, the headroom is the minimum of
each ancestor's headroom plus `C`'s own headroom (i.e.
`min(quota - used)` over the whole chain), and the counter on `C` is
bumped by exactly that minimum. The `W_THROTTLED` diagnostic still
carries `cgroup_id = C` (the consume target, not the bottleneck), with
`amount_dropped = amount - bumped`.

## `"sum_children_capped"`

Identical to `"independent"` for the consume-time check (only `C`'s own
quota is examined), but with one extra invariant enforced at `create`,
`update_quota`, and `move_subtree` time: the SUM of every direct child's
declared `mem_quota_kb` must not exceed the parent's `mem_quota_kb`.
When a `create`, `update_quota`, or `move_subtree` would cause this sum
to exceed the parent's `mem_quota_kb`, emit
`E_QUOTA_SUM_EXCEEDS_PARENT` and skip the event (no state change).
This check is run only on `mem_quota_kb`; cpu and iops quotas are not
sum-capped.

The `E_QUOTA_SUM_EXCEEDS_PARENT` check fires AFTER `E_BELOW_MIN_QUOTA`
on `create` and `update_quota`, and AFTER `E_CYCLE_REJECTED` on
`move_subtree`. When the inheritance mode is `"strict"` or
`"independent"` this check is suppressed entirely.

## Over-Quota Action Summary

When a consume violates the quota check (either the cgroup's own under
`independent`/`sum_children_capped` or any cgroup in the chain under
`strict`):

- `"reject"`: emit `E_OVER_QUOTA`, no state change. `cgroup_id` is the
  bottleneck cgroup (which is `C` itself except under `strict` where it
  may be an ancestor).
- `"throttle"`: increment by the headroom (which can be 0), emit
  `W_THROTTLED` with `cgroup_id = C` (the consume target, regardless of
  the inheritance mode) and `amount_dropped = amount - bumped`.

The peak update on `consume_cpu`/`consume_mem` uses `bumped`, so a
fully-rejected consume does NOT update the peak, and a partially-throttled
consume updates the peak by the partial amount.
