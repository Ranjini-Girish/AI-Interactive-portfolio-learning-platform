# Output Format

Write a single JSON file to `/app/output/bundle_report.json` with two-space indentation and a trailing newline.

## Top-level keys

The report has four top-level keys: `module_graph`, `tree_shaking`, `chunks`, and `summary`.

### module_graph

- `total_modules` — integer, count of internal (non-external) modules.
- `external_packages` — sorted array of external package name strings.
- `has_circular_imports` — boolean.
- `circular_chains` — array of cycle arrays. Each cycle is an array of module IDs starting and ending with the same ID (alphabetically smallest first). Sorted by first differing element.

### tree_shaking

- `reachable_modules` — sorted array of reachable internal module IDs.
- `dead_modules` — sorted array of dead internal module IDs.
- `used_exports` — object keyed by module ID (only reachable modules). Each value is a sorted array of used export name strings. Omit dead modules.
- `dead_exports` — array of `{ "module": string, "name": string, "size_bytes": number }` objects, sorted by `module` then `name`.
- `total_raw_size_bytes` — integer.
- `total_tree_shaken_size_bytes` — integer.
- `shake_savings_bytes` — integer.

### chunks

- `entry` — object with `modules` (sorted array of module IDs) and `size_bytes` (integer).
- `async_chunks` — array of objects sorted by `name`, each with:
  - `name` — string `"async-<target_module_id>"`.
  - `trigger_module` — the dynamically imported module ID.
  - `trigger_source` — the module ID that contains the dynamic import.
  - `modules` — sorted array of module IDs in this chunk.
  - `size_bytes` — integer.
- `shared` — object with `modules` (sorted array) and `size_bytes` (integer). If no shared modules exist, `modules` is empty and `size_bytes` is 0.

### summary

- `total_modules` — integer, same as `module_graph.total_modules`.
- `reachable_modules` — integer, count of reachable modules.
- `dead_modules` — integer, count of dead modules.
- `total_chunks` — integer, count of all chunks (entry + async + shared, counting shared only if non-empty).
- `entry_size_bytes` — integer.
- `async_sizes_bytes` — array of integers (one per async chunk, same order as `chunks.async_chunks`).
- `shared_size_bytes` — integer (0 if no shared chunk).
- `total_bundle_size_bytes` — integer, sum of all chunk sizes.
- `total_raw_size_bytes` — integer.
- `shake_savings_bytes` — integer.
- `shake_savings_percent` — float rounded to `savings_decimal_places` from config.
