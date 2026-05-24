# Chunk Assignment & Sizing Rules

## Chunk types

1. **Entry chunk** — contains all modules statically reachable from entry points (following only static import edges, not dynamic imports).
2. **Async chunks** — one per dynamic import target. Contains the target module and any modules reachable from it via static imports that are **not** already in the entry chunk and not assigned to the shared chunk.
3. **Shared chunk** — contains modules that are reachable from **two or more** async chunks (but not the entry chunk) and whose tree-shaken size meets or exceeds `min_shared_size_bytes` from config. Modules below the threshold are duplicated into each async chunk that needs them.

## Assignment algorithm

1. Compute the entry set: all modules reachable from entry points via static imports only.
2. For each dynamic import target (in alphabetical order of target module ID), compute its async set: all modules reachable from the target via static imports that are **not** in the entry set.
3. Identify shared candidates: modules that appear in two or more async sets. For each candidate, compute its tree-shaken size. If the size is >= `min_shared_size_bytes`, move it to the shared chunk and remove it from all async sets. Otherwise, leave it duplicated in each async set.
4. Dead modules belong to no chunk.

## Async chunk naming

Each async chunk is named `"async-<target_module_id>"`. The `trigger_source` is the module ID that contains the dynamic import pointing to this target.

## Chunk size calculation

Each chunk's `size_bytes` is the sum of tree-shaken sizes of all modules assigned to that chunk. Only used exports contribute to a module's tree-shaken size within the chunk.

## Module lists

All module lists within chunks are sorted alphabetically by module ID.

## Async chunk ordering

Async chunks in the output array are sorted alphabetically by their `name` field.
