# Tree-Shaking Analysis Specification

## Overview

Tree-shaking determines which modules and exports are reachable from the configured entry points. Unreachable modules and unused exports can be eliminated from the bundle.

## Reachability Algorithm

1. Start with the set of entry point modules as "reachable."
2. For each reachable module, examine its static imports and re-exports:
   - The target module of each import/re-export becomes reachable.
   - Recurse into newly reachable modules.
3. Dynamic imports (`import('...')`) also make their target modules reachable.
4. Continue until no new modules are added.

A module is "unreachable" if it is never reached from any entry point via any import chain (static or dynamic).

## Used Export Tracking

For each reachable module, determine which of its exports are "used":

1. **Named imports**: `import { foo } from './mod.js'` marks `foo` as used in `mod.js`.
2. **Default imports**: `import def from './mod.js'` marks `default` as used in `mod.js`.
3. **Namespace imports**: `import * as ns from './mod.js'` marks ALL named exports of `mod.js` as used (but NOT the default export).
4. **Side-effect imports**: `import './mod.js'` makes the module reachable but does NOT mark any exports as used.
5. **Re-export named**: `export { foo } from './mod.js'` marks `foo` as used in `mod.js` ONLY IF the re-exporting module itself has `foo` (or the re-exported alias) marked as used.
6. **Re-export all**: `export * from './mod.js'` — the re-exported names from `mod.js` are marked as used in `mod.js` only if they are used (imported) from the re-exporting module by some other module.
7. **Dynamic imports**: `import('./mod.js')` marks ALL named exports AND the default export of `mod.js` as used (conservative assumption since the consumer is unknown).

## Used Export Propagation for Re-exports

When a module uses re-exports (`export * from` or `export { x } from`), the "used" status must propagate through the chain:

1. If module A does `export * from './B.js'` and module C does `import { foo } from './A.js'`, then `foo` is marked as used in BOTH A and B (since A is re-exporting it from B).
2. Follow re-export chains to their origin. If B also does `export * from './D.js'`, check D for `foo` as well.
3. `export *` does NOT propagate `default` exports — only named exports.

## Output

- `reachable_modules`: Sorted list of module_ids reachable from entry points.
- `unreachable_modules`: Sorted list of module_ids NOT reachable. (A module is unreachable only if it exists in the codebase but is never imported by any reachable module.)
- `used_exports`: Object mapping module_id to a sorted array of used export names.
- `unused_exports`: Object mapping module_id to a sorted array of unused export names. Only include modules that have at least one unused export.
- `original_size`: Sum of source_size for ALL modules.
- `tree_shaken_size`: Sum of source_size for reachable modules only.
- `savings_ratio`: round((original_size - tree_shaken_size) / original_size, output_precision). If original_size is 0, savings_ratio is 0.0.
