# Realloc Specification

## Overview

`realloc(id, new_size, align)` changes the size of an existing allocation. The alignment for the reallocated block uses the provided `align` parameter.

## In-Place Expansion

If `new_size > current_user_size` (growth):

1. Compute the new aligned size: `new_aligned = round_up(new_size, align)`.
2. Compute the new required block size: `header_size + new_aligned`.
3. Check if the block immediately following the current allocation is free.
4. If the following block is free and `current_block_size + following_free_block_size >= new_required_size`, expand in place:
   - Absorb (part of) the following free block.
   - If the remainder of the following free block after expansion is >= `header_size + min_alignment`, split it into a new smaller free block.
   - Otherwise, absorb the entire following free block (excess is internal fragmentation).
5. If in-place expansion is not possible, fall back to alloc-copy-free: allocate a new block of `new_size` with `align`, copy the old user data, then free the old block. If the new allocation fails (OOM), the realloc fails and the old block is unchanged.

## In-Place Shrink

If `new_size < current_user_size` (shrink) or if alignment changes make the new aligned size smaller:

1. Compute the new aligned size and new required block size.
2. If `current_block_size - new_required_size >= header_size + min_alignment`, split: the current block shrinks to the new required size, and the remainder becomes a new free block (which may then coalesce with the following block if it is also free).
3. Otherwise, keep the current block size unchanged. The excess is internal fragmentation.

## Same Size

If `new_aligned == current_aligned_size`, the realloc is a no-op. The block is unchanged.

## Error Cases

Realloc on a freed or never-allocated ID is a use-after-free error.
