# Output Format Specification

The output file must be valid JSON with:
- 2-space indentation
- Keys sorted alphabetically at ALL nesting levels
- Trailing newline

## Top-Level Schema

```json
{
  "cycles": [...],
  "dependency_graph": {...},
  "modules": {...},
  "summary": {...},
  "unreachable_modules": [...],
  "unused_exports": [...]
}
```

## Field Details

### dependency_graph
Object mapping module name -> sorted array of module names it imports from.
Only internal modules (relative path imports). Module names are filenames
relative to src/ (e.g., "auth.js", "handlers/user.js").

### modules
Object mapping module name -> object with:
- "exports": sorted array of exported symbol names (use "default" for default exports)
- "import_count": number of internal import statements
- "imports": sorted array of objects {"source": "mod.js", "symbols": [...], "type": "named|default|namespace|side-effect|re-export"}
  The `symbols` array content depends on the import type:
  - `named`: the imported symbol names (e.g., `["x", "y"]`); for aliased imports (`x as y`), use the original name (`x`)
  - `default`: `["default"]`
  - `namespace`: `["*"]`
  - `side-effect`: `[]` (empty array)
  - `re-export`: `["default"]` for `export { default as Name } from`, `["*"]` for `export * from`, or the named symbols for `export { x, y } from`
- "reachable": boolean (reachable from any entry point via transitive imports)

### cycles
Array of cycle arrays. Each cycle is the sorted list of module names forming
a strongly connected component of size >= 2. Outer array sorted lexicographically.

### unused_exports
Array of objects {"module": "mod.js", "symbol": "name"}, sorted by module then symbol.
An export is unused if no other module imports it (directly or via namespace/re-export).

### unreachable_modules
Sorted array of module names not reachable from any entry point.

### summary
- "cycle_count": number of cycles
- "max_depth": longest shortest-path from any entry point to any reachable module
- "reachable_count": number of reachable modules
- "side_effect_imports": total side-effect import statements across all modules
- "total_exports": total export count across all modules
- "total_imports": total import statement count (internal only) across all modules
- "total_modules": number of .js files analyzed
- "unreachable_count": number of unreachable modules
- "unused_export_count": number of unused exports
