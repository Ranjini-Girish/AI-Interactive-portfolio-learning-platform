# Anti-Replay Window Overview

The simulator models the inbound anti-replay layer of an IPsec-style fleet.
Each Security Association (SA) carries an opaque string `id`, a 64-bit
non-negative integer `top` (the highest ESP sequence number this SA has ever
accepted), an integer `window_size` chosen from `policy.window_sizes_allowed`,
a string `owner` (the authenticated peer or tenant), and a `bitmap` covering
the last `window_size` sequence numbers below `top`.

The bitmap is laid out so that bit position 0 represents `top` itself, bit
position 1 represents `top - 1`, and so on up to bit position
`window_size - 1`, which represents `top - window_size + 1`. The bitmap is
exactly `window_size` bits wide, padded up to a whole number of bytes for
serialisation. An SA whose `top` is 0 has never accepted a packet -- its
bitmap is all-zero and the entire window is empty.

`sas.json` is the initial SA table. Once an SA `id` has been observed
anywhere in the trace (declared in `sas.json`, added by `add_sa`, or
created passively by `recv` under `on_unknown_sa == "create_passive"`),
that id can never be reintroduced -- a later `add_sa` for the same id
emits `E_DUPLICATE_SA` even if the previous holder was already deleted.

`events.json` is a strictly ascending list of operations (`seq` 0..N-1, dense)
that drive the table. Events are processed in `seq` order, one at a time. A
diagnostic-emitting event does not change SA state -- when an event fails its
preconditions, the simulator emits the documented diagnostic for that event
and moves on. Only `recv` events emit a row in `packet_decisions.json`.
