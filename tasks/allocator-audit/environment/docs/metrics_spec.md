# Metrics Specification

All metrics are computed at the end of processing a trace (after all operations).

## External Fragmentation

`external_fragmentation = 1.0 - (largest_free_block_usable / total_free_usable)`

Where:
- `largest_free_block_usable` is the usable size (total size minus header) of the largest free block.
- `total_free_usable` is the sum of usable sizes across all free blocks.

If `total_free_usable == 0` (no free space), external fragmentation is 0.0.

The usable size of a free block is `block_total_size - header_size`. This is the maximum payload that could be allocated from that block (before alignment considerations).

## Internal Fragmentation

`internal_fragmentation = total_padding / total_allocated_block_size`

Where:
- `total_padding` is the sum of `(aligned_size - requested_size)` for all currently live (not freed) allocations. For blocks that were not split and have extra leftover space, that leftover is also included in padding: `padding = block_total_size - header_size - requested_size`.
- `total_allocated_block_size` is the sum of total block sizes (including header) of all live allocations.

If there are no live allocations, internal fragmentation is 0.0.

## High-Water Mark

The maximum total of `requested_size` values summed across all simultaneously live allocations at any point during the trace. This tracks only the user-requested bytes, not headers or alignment padding.

## Pool Utilization

`pool_utilization = total_allocated_block_size / pool_size`

Where `total_allocated_block_size` is the sum of total block sizes (header + aligned payload, or the unsplit block size) for all live allocations at the end of the trace.

## Free Block Count

The number of distinct free blocks in the free list at the end of the trace.

## Largest Free Block

The usable size of the largest free block at the end of the trace (0 if no free blocks).

## Rounding

Round all float metrics to six decimal places.
