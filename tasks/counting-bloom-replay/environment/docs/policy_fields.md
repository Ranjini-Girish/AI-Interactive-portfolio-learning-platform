# Policy Fields

`policy.json` is a flat object with six required fields. The simulator
must branch on every one of them; hardcoding a single value of any
field will fail the byte-exact comparison on any input that exercises
the other branch.

## `m`

The number of counter slots in the array. Positive integer; the array
length at the start of replay. May change mid-run via a `resize` event.

## `k`

The number of double-hashing positions per key. Positive integer. May
change mid-run via a `resize` event.

## `counter_bits`

One of `2`, `3`, `4`, `8`. Each counter is an unsigned integer in
`[0, 2^counter_bits - 1]`. The maximum value
`max_v = 2^counter_bits - 1` is what `saturation_action == "saturate"`
clamps to and what `saturation_action == "reject"` checks against.
`counter_bits` is fixed for the entire run — `resize` does NOT change
it.

## `hash_family`

A constant string `"fnv1a_double_hashing"`. The recipe is documented in
`/app/docs/hash_family.md`. Any other value is malformed input and the
binary must exit non-zero.

## `saturation_action`

One of `"reject"` or `"saturate"`. The branch fires on every `add`
event (including the synthetic adds the simulator runs during a
`resize`). See `/app/docs/events.md` for the exact branch behavior.

## `remove_below_zero_action`

One of `"reject"` or `"clamp"`. The branch fires on every `remove`
event. See `/app/docs/events.md` for the exact branch behavior.

## What the policy does NOT include

The policy does not describe a TTL, a hash seed, a per-key salt, a
random-eviction parameter, a clock, or anything else. The replay is a
function of `(keys, events, policy)` alone.
