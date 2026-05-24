# Alignment Specification

## Rounding Rules

When an allocation request specifies a size `S` and alignment `A`:

1. The user payload size is rounded up to the nearest multiple of `A`. Call this `aligned_size`. Formally: `aligned_size = ((S + A - 1) / A) * A`, using integer division.
2. For zero-size allocations (`S == 0`), `aligned_size` is 0. The block still consumes `header_size` bytes for the header.
3. The total block size consumed from the pool is `header_size + aligned_size`.

## Header Alignment

The header itself does not require additional alignment padding. Headers are always placed at the next available address after the preceding block ends. The `header_size` is guaranteed to be a multiple of `min_alignment` in the pool configuration.

## Internal Fragmentation from Alignment

The difference `aligned_size - S` is the alignment padding for that allocation. This counts as internal fragmentation attributed to that block.
