# First-Fit Allocator Specification

The allocator manages a contiguous memory pool of configurable size. The pool is a flat byte array starting at address 0.

## Block Structure

Every block (allocated or free) carries a fixed-size header immediately before the user-visible region. The header size is specified in `pool_config.json` (field `header_size`). The header stores the block's total size (header + user payload + alignment padding) and its allocation state.

The user-visible address of a block is `block_start + header_size`.

## Initial State

At startup the pool contains a single free block spanning the entire pool. This block has one header at address 0; the usable region begins at address `header_size`.

## Allocation (first-fit)

1. Walk the free list from lowest address to highest.
2. For each free block, compute the aligned allocation size (see `alignment_spec.md`).
3. The required block size is `header_size + aligned_user_size`.
4. If the free block's total size >= required block size, select it.
5. If the remainder after carving out the required block is >= `header_size + min_alignment`, split the free block: the first part becomes the allocated block, the second part becomes a new free block with its own header.
6. If the remainder is smaller than `header_size + min_alignment`, do not split. The entire free block becomes the allocated block. The excess bytes are internal fragmentation (padding).
7. If no free block is large enough, the allocation fails (OOM).

## Free List

The free list is maintained in address order (ascending by block start address). It is not a linked list in memory; it is a logical ordering of all free blocks sorted by their position in the pool.
