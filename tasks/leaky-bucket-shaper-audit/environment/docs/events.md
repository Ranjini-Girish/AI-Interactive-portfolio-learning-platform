# Event semantics

All events are records `{ "seq": <int>, "type": <string>, ... }`.
`seq` must be dense from `0`. Unknown event types and extra/missing
fields are malformed.

## `submit`

Fields: `seq`, `type="submit"`, `bucket_id`, `size_bytes`.

* `bucket_id` — must reference an existing bucket; otherwise emit
  `E_UNKNOWN_BUCKET` and drop the request (do not modify any bucket
  state).
* `size_bytes` — integer in `[1, 10^9]`.
* If `current_bytes + size_bytes <= capacity_bytes`: admit. Set
  `current_bytes += size_bytes`. Append an admit record
  `{seq, bucket_id, size_bytes, level_after}`. Emit `N_ADMITTED`.
* Otherwise: reject entirely (no partial admit). Emit
  `W_DROPPED_OVERFLOW` with detail `<size_bytes>`. Track
  `dropped_bytes_total += size_bytes` only when
  `policy.count_dropped_bytes=true`; otherwise keep the diagnostic
  but leave `dropped_bytes_total=0`.

## `tick`

Fields: `seq`, `type="tick"`. Increment `now_ticks` by `1`. Then for
every bucket, in `bucket_id` lex order, compute
`current_bytes = max(0, current_bytes - leak_bytes_per_tick)`. No
diagnostic is emitted on its own when level reaches zero.

## `reconfigure`

Fields: `seq`, `type="reconfigure"`, `bucket_id`, `new_capacity_bytes`,
`new_leak_bytes_per_tick`.

* `bucket_id` must reference an existing bucket — otherwise the
  simulator exits non-zero (this is malformed input, since bucket
  identity is part of the closed contract).
* `new_capacity_bytes` ∈ `[1, 10^9]`,
  `new_leak_bytes_per_tick` ∈ `[0, 10^9]`.
* Apply the new parameters. If the new capacity is strictly less than
  the current level, immediately truncate
  `current_bytes = new_capacity_bytes` and emit `W_CAPACITY_REDUCED`
  with detail `<old_level>-><new_capacity_bytes>`.
* If neither parameter changes from the prior value, emit
  `W_RECONFIG_NOOP` with detail `<bucket_id>`.
