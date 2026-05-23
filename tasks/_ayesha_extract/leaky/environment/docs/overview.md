# Leaky Bucket Shaper Replay — Overview

You are simulating a per-bucket byte-based leaky-bucket traffic shaper.
Each bucket has a `capacity_bytes` ceiling and a `leak_bytes_per_tick`
drain rate; a `submit` event tries to add bytes to the bucket level,
admitted if and only if the post-add level stays within capacity.
Otherwise the entire submit is dropped — no partial admission.

Inputs:

* `/app/data/buckets.json` — bucket configuration.
* `/app/data/events.json` — dense `seq` event stream.
* `/app/data/policy.json` — knobs.

Outputs in `/app/output/`:

* `bucket_state.json` — final per-bucket level + parameters.
* `admits.json` — admit log; empty when `track_admits=false`.
* `shaper_diagnostics.json` — sparse diagnostics (warns/notes/errors).
* `summary.json` — counters.

## Buckets (`buckets.json`)

* `bucket_id` — unique, `^[A-Za-z0-9._-]{1,32}$`.
* `capacity_bytes` — integer in `[1, 10^9]`.
* `leak_bytes_per_tick` — integer in `[0, 10^9]`.

## State

* `now_ticks` starts at `0` and advances by `1` for every `tick`.
* Each bucket has a `current_bytes` level (initially `0`).
* `submit` events never modify level partially: if the request would
  push past capacity, the request is rejected entirely.

## Event execution rules

Events are processed in `seq` order (dense from `0`). Each event must
strictly conform to the schemas in `/app/schemas/`. Anything else
(non-dense `seq`, unknown `type`, extra/missing fields, `bucket_id`
referencing an unknown bucket in `reconfigure`, malformed
`policy.json`/`buckets.json`) terminates the simulator non-zero.

Per-event behavior is documented in `events.md`.
