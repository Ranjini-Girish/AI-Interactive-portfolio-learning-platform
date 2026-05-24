# Re-Export Resolution Specification

## Types of Re-Exports

### Named Re-Export
```
export { name1, name2 } from './module.js';
```
Re-exports specific named bindings from the source module.

### Default-as-Named Re-Export
```
export { default as newName } from './module.js';
```
Re-exports the default export of the source module as a named export. Record the original name as "default" and the alias as "newName".

### Wildcard Re-Export
```
export * from './module.js';
```
Re-exports ALL named exports from the source module. Crucially, this does NOT re-export the `default` export.

## Transitive Re-Export Resolution

When resolving what names a module actually exports (including through re-exports), follow re-export chains:

1. Start with the module's own `named_exports` and `has_default_export`.
2. For each `export { name } from './source.js'`:
   - The module exports `name` (or its alias) as if it were its own.
3. For each `export * from './source.js'`:
   - Add all named exports from `source.js` to this module's effective exports.
   - If `source.js` also has `export * from './other.js'`, follow that chain too.
   - Do NOT include `default` exports in wildcard re-exports.
4. Stop following chains when you encounter a module already visited (cycle protection).

## Effective Exports

The "effective exports" of a module are:
- Its own named exports (from `export const/let/var/function/class`)
- Its own default export (if any)
- Named exports gained through `export { x } from` re-exports
- Named exports gained through `export * from` chains (excluding defaults)

The `re_exports` field in the output lists the re-export declarations, NOT the resolved effective exports. The tree-shaking analysis uses effective exports for propagation.
