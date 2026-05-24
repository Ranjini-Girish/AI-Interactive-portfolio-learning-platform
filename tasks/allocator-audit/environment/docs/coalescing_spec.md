# Coalescing Specification

## Immediate Coalescing

When a block is freed, the allocator immediately attempts to merge it with adjacent free blocks.

## Merge Procedure

1. Check the block immediately following the freed block in memory. If it is free, merge: the freed block absorbs the neighbor's entire region including its header. The merged block's total size is `freed_block_size + neighbor_block_size`.
2. Check the block immediately preceding the freed block in memory. If it is free, merge: the preceding free block absorbs the freed block's entire region including its header. The merged block's total size is `preceding_block_size + freed_block_size` (after any right-merge from step 1).
3. The resulting free block is placed in the free list at the address of the leftmost (lowest-address) block involved in the merge.

## Header Reclamation

When blocks are merged, the headers of absorbed blocks become part of the usable free region. For example, merging two adjacent free blocks of size `X` and `Y` produces a single free block of size `X + Y`, not `X + Y - header_size`. The absorbed block's header bytes are reclaimed as free space within the merged block.
