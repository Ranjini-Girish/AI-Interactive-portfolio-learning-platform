# Module Definition Format

Each `.json` file in `/app/data/modules/` defines one module with these fields:

- **id** — unique module identifier (string), e.g. `"src/app"`.
- **base_size_bytes** — overhead size in bytes for the module itself, independent of its exports.
- **exports** — array of `{ "name": string, "size_bytes": number }` objects representing the module's exported symbols.
- **imports** — array of import descriptors:
  - `"module"` — target module ID.
  - `"names"` — array of imported symbol names. The special value `"*"` (as a single-element array `["*"]`) denotes a namespace import, which marks **all** exports of the target module as used.
  - `"external"` — optional boolean. When `true`, the target is an external package excluded from bundle analysis.
- **dynamic_imports** — array of module IDs loaded asynchronously. Each dynamic import creates an async chunk boundary.
- **side_effects** — boolean. When `true`, the module must be included in the bundle if it appears anywhere in the reachable import graph, even if none of its exports are used by any other module. Its unused exports are still excluded from size calculations.
