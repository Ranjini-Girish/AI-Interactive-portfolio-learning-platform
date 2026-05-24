# Tree-Shaking Rules

## Reachability

Starting from each entry point in `config.json`, follow **static** import edges to determine the set of statically reachable modules. Then follow dynamic import targets from reachable modules to discover additional reachable modules (these become async-chunk roots). Continue recursively: any module reachable via static imports from an async-chunk root is also reachable.

A module is **dead** if it is not reachable from any entry point through any combination of static and dynamic import chains.

## Export usage analysis

An export `E` from module `M` is **used** if any reachable module has a static import entry referencing `M` with `E` in its `names` array.

Special case — namespace imports: if a reachable module imports `M` with `names: ["*"]`, then **every** export of `M` is marked as used.

Special case — dynamic imports: when a reachable module lists `M` in its `dynamic_imports`, **all** exports of `M` are marked as used, because the dynamic `import()` call returns the full module namespace.

An export is **dead** if it is not used by any reachable module through any of the above mechanisms. Exports of dead modules are also dead.

## Side effects

A module with `side_effects: true` is included in the bundle (its `base_size_bytes` counted) whenever it is reachable, regardless of whether any of its exports are used. However, individual unused exports of such a module are still excluded from size calculations.

A module with `side_effects: false` that is reachable but has **zero** used exports is still included (its base_size_bytes counted) because it was explicitly imported — side_effects only controls whether a module *without any import edges leading to it* would be kept, which is handled by the reachability check.

## Size calculations

- **Raw size** of a module: `base_size_bytes` + sum of all export `size_bytes`.
- **Tree-shaken size** of a reachable module: `base_size_bytes` + sum of **used** export `size_bytes`.
- **Tree-shaken size** of a dead module: 0.
- **total_raw_size_bytes**: sum of raw sizes across all internal modules.
- **total_tree_shaken_size_bytes**: sum of tree-shaken sizes across all reachable modules.
- **shake_savings_bytes**: `total_raw_size_bytes - total_tree_shaken_size_bytes`.
- **shake_savings_percent**: `round(shake_savings_bytes / total_raw_size_bytes * 100, savings_decimal_places)` from config.

## Dead exports list

Report each dead export as `{ "module": module_id, "name": export_name, "size_bytes": N }`. Sort the list by `module` ascending, then `name` ascending.
