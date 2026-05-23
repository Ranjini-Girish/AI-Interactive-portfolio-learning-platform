# Event Semantics

Events arrive in `events.json["events"]` already sorted by a strictly
ascending dense `seq` starting at `1`. The simulator MUST replay them in
that order; reordering by `op` or by `key_idx` is forbidden.

There are exactly six legal `op` values. Any other value is malformed
input and the binary must exit non-zero.

## `add`

Schema fields: `seq`, `op = "add"`, `key_idx`.

Resolve the key: `key = keys[key_idx]`. Compute the `k` positions from
`/app/docs/hash_family.md`.

Decision under `policy.saturation_action`:

- `"reject"`: if **any** of the `k` resolved positions is currently equal
  to `2^counter_bits - 1`, reject the entire add. Counters and ground-truth
  multiset are unchanged. Diagnostic: `D_REJECTED_SATURATE`. Bumps
  `rejected_saturate`.
- `"saturate"`: increment each of the `k` positions by 1. A position that
  is already at `2^counter_bits - 1` stays at `2^counter_bits - 1` (the
  counter caps; this loses information for that key). Bumps
  `successful_adds` and increments `multiset_count[key]`. Diagnostic:
  `D_OK_ADD`.

The position multiset rule from `/app/docs/hash_family.md` applies: if two
of the `k` positions collide, both increments still hit that single slot.

## `remove`

Schema fields: `seq`, `op = "remove"`, `key_idx`.

Resolve the key and compute the `k` positions exactly as for `add`.

Decision under `policy.remove_below_zero_action`:

- `"reject"`: if **any** of the `k` resolved positions is currently zero,
  reject the entire remove. Counters and ground-truth multiset are
  unchanged. Diagnostic: `D_REJECTED_NEGATIVE`. Bumps `rejected_negative`.
- `"clamp"`: decrement each of the `k` positions by 1, clamping at zero
  (so a position that was already zero stays at zero rather than
  underflowing). The ground-truth `multiset_count[key]` is decremented by 1
  *only if it is currently positive* (so the ground truth never goes
  negative either). Bumps `clamped_remove` if at least one of the `k`
  positions was clamped at zero, otherwise bumps `successful_removes`.
  Diagnostic: `D_CLAMPED_REMOVE` if any clamp fired, otherwise `D_OK_REMOVE`.

The position multiset rule applies exactly as for `add`.

## `query`

Schema fields: `seq`, `op = "query"`, `key_idx`.

Resolve the key and compute the `k` positions. The predicted membership
is `true` if and only if every one of the `k` positions has a counter
> 0. The ground-truth membership is `multiset_count[key] > 0`.

The outcome is one of `"tp"`, `"fp"`, `"tn"`, `"fn"`:

- `"tp"`: predicted true, ground-truth true.
- `"fp"`: predicted true, ground-truth false.
- `"tn"`: predicted false, ground-truth false.
- `"fn"`: predicted false, ground-truth true. This is only possible when
  `policy.saturation_action == "saturate"` and a saturated counter has
  since been decremented past the saturation point — counting Bloom
  filters lose information at saturation.

Bumps `successful_queries` either way. Diagnostic: `D_OK_QUERY`.

## `clear`

Schema fields: `seq`, `op = "clear"` (no `key_idx`).

Zero every counter in the array and zero `multiset_count[key]` for every
key. Bumps `clears`. Diagnostic: `D_OK_CLEAR`.

## `resize`

Schema fields: `seq`, `op = "resize"`, `new_m`, `new_k`. Both must be
positive integers.

Replace `m` with `new_m` and `k` with `new_k`. Allocate a fresh counter
array of length `new_m`, all zeros. Then, for every key `key` in the
key universe whose `multiset_count[key] > 0`, replay
`multiset_count[key]` synthetic `add` operations against the new array
under the same `saturation_action`. Iterate over keys in their `key_idx`
order (i.e. their order in `keys.json`). Each synthetic add increments
`successful_adds` or `rejected_saturate` exactly as it would for an
ordinary `add`; the ground-truth `multiset_count` is unchanged by a
saturate-rejection (i.e. for `"reject"` mode a synthetic add that would
saturate is dropped from the ground truth too, so a `resize` that
saturates may legitimately reduce the represented multiset). Bumps
`resizes`. Diagnostic: `D_OK_RESIZE`.

## `dump_stats`

Schema fields: `seq`, `op = "dump_stats"`.

Append a snapshot to `stats_dumps.json` (see
`/app/docs/output_format.md`). The snapshot is a function of the
state at the *moment of the event* — taking it does not mutate state.
Diagnostic: `D_OK_DUMP`.
