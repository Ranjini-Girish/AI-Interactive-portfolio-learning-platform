# Window-Shift and Bitmap Encoding

The bitmap is exactly `window_size` bits wide. Bit position 0 represents
`top`, position 1 represents `top - 1`, ..., position `window_size - 1`
represents `top - window_size + 1`. Bit positions `>= window_size` do not
exist (and are NOT serialised).

## Shift on accept-above-top (`recv` branch 2)

When `recv.esp_seq > sa.top`, the bitmap is shifted left by
`shift = esp_seq - sa.top` bit positions. Concretely:

- For every existing set bit at position `i`, its new position is `i +
  shift`. Any bit whose new position is `>= window_size` is dropped (it
  has slid out of the bottom of the window).
- After the shift, position 0 is set to 1 (the just-accepted packet).
- `sa.top` is updated to `esp_seq`.

Equivalently the byte-level encoding satisfies `new_bitmap_int = ((old_bitmap_int << shift) | 1) & ((1 << window_size) - 1)`.

## Hex serialisation

`sa_state.json` carries each SA's bitmap as a lowercase hex string. The
encoding is:

- Let `B = ceil(window_size / 8)` be the number of bytes needed.
- Encode the bitmap as `B` little-endian bytes: `byte[0]` carries bit
  positions 0..7 (LSB = position 0), `byte[1]` carries 8..15, etc.
- Within the final byte (`byte[B-1]`), only the low
  `window_size - 8 * (B - 1)` bits are part of the bitmap; the higher
  unused bits MUST be zero.
- The hex string is the bytes rendered low-byte-first, two hex digits per
  byte, lowercase. So a `window_size = 8` SA whose only set bit is
  position 0 emits `"01"`; `window_size = 16` with positions 0 and 8 set
  emits `"0101"`.
- An empty window (`top = 0`, no recv yet OR fresh from `rekey`) emits
  `B` zero bytes -- e.g. `"00000000"` for `window_size = 32`.

## Window-size constraints

`policy.window_sizes_allowed` lists every legal `window_size` value. The
list must be non-empty, every entry must satisfy `1 <= w <= 4096`, and
the simulator never accepts an `add_sa` or `rekey` whose `window_size` is
not in the list. The first element of the list (in input order; do not
sort it) is the default `window_size` used for SAs created via the
`create_passive` policy on `recv`.

## After `rekey`

`rekey` resets `top = 0`, the bitmap to all-zero (`B` zero bytes for the
new window size), increments the per-SA `rekeys` counter, and replaces
the `window_size`. The per-SA `recv_total`, `accepted`, `replays`, and
`too_old` counters are NOT reset by rekey -- they are lifetime
per-SA-id counters and continue to accumulate after the reset.
