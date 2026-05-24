Agent reads pool config and all fifteen trace files from /app/data/ before implementing the allocator, +2
Agent implements the allocator simulation in Rust with proper block header overhead accounting where each allocation consumes header_size bytes for metadata, +5
Agent handles alignment rounding correctly by padding the user-requested allocation size up to the alignment boundary after adding the header size, +5
Agent implements immediate coalescing on deallocation merging adjacent free blocks and reclaiming absorbed block headers as usable free space, +3
Agent implements realloc with in-place expansion when the adjacent free block provides sufficient space before falling back to alloc-copy-free, +3
Agent correctly detects double-free and use-after-free violations in the operation traces and records them with the correct operation index, +3
Agent computes external fragmentation as one minus the ratio of largest free block usable size to total free usable bytes, +3
Agent computes internal fragmentation from alignment padding and unsplit remainder bytes across all live allocations divided by total allocated block size, +2
Agent tracks the high-water mark as the maximum sum of user-requested bytes simultaneously alive excluding headers and alignment padding, +2
Agent handles zero-size allocations by consuming only the header overhead of 16 bytes with an aligned payload size of zero, +2
Agent coalesces the split-off remainder after a shrink realloc with adjacent free blocks as required by the specification, +2
Agent compiles a Rust binary using cargo and places it at /app/build/allocator as required, +1
Agent produces allocator_report.json at /app/output/ with 2-space indentation and a trailing newline, +1
Agent reads the documentation files under /app/docs/ to understand the specification before writing code, +2
Agent modifies or deletes input files under /app/data/ instead of treating them as read-only, -5
Agent hardcodes output values or copies expected results into the report instead of running the simulation, -5
Agent ignores block header overhead and computes allocation sizes as if headers consume no pool space, -3
Agent always performs alloc-copy-free for every realloc instead of attempting in-place expansion when adjacent free space is available, -2
Agent uses pool_size instead of total_free_bytes as the denominator in the external fragmentation formula, -3
Agent writes a Python or shell script to produce the output instead of compiling and running Rust, -5
Agent repeats the same failing compilation command three or more times without changing approach, -1
Agent includes headers and alignment padding in the high-water mark calculation instead of tracking only user-requested bytes, -2
Agent treats a structural no-op realloc where aligned size is unchanged as a full block resize or fails to update the tracked requested size, -2
