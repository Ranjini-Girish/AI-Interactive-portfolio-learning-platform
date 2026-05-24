# Module Metrics Specification

## Source Size

`source_size` is the number of bytes (characters) in the module's source file, as read from disk. Use UTF-8 encoding.

## Per-Module Fields

For each module, compute:

- `module_id`: The filename relative to the base_path (e.g., "index.js", "auth.js").
- `source_size`: File size in bytes.
- `named_exports`: Sorted list of named export identifiers declared by this module. This includes names from `export const/let/var/function/class` declarations. For re-exports (`export { x } from` or `export * from`), the re-exported names are NOT listed here — they appear in `re_exports` instead.
- `has_default_export`: Boolean indicating whether the module has an `export default` declaration.
- `re_exports`: Array of re-export descriptors, each with:
  - `source`: The source module_id being re-exported from
  - `names`: Sorted array of specific names being re-exported (empty array for `export * from`)
  - `is_all`: Boolean — true for `export * from`, false otherwise
- `static_imports`: Array of static import descriptors, each with:
  - `source`: The source module_id
  - `specifiers`: Array of specifier objects, each with:
    - `type`: "named", "default", or "namespace"
    - `name`: The imported name ("default" for default imports, "*" for namespace)
  Sorted by source module_id.
- `dynamic_imports`: Sorted array of module_ids imported dynamically.
- `afferent_coupling`: As defined in graph_spec.md.
- `efferent_coupling`: As defined in graph_spec.md.
- `instability`: As defined in graph_spec.md.
- `layer`: Topological layer on the condensation DAG, as defined in graph_spec.md.

## Summary Fields

- `total_modules`: Count of all modules.
- `total_static_edges`: Count of static dependency edges.
- `total_dynamic_edges`: Count of dynamic dependency edges.
- `circular_dependency_count`: Number of SCCs with 2+ members.
- `total_named_exports`: Sum of named_exports array lengths across all modules.
- `total_re_exports`: Count of re-export descriptors across all modules.
- `modules_with_default_export`: Count of modules where has_default_export is true.
- `side_effect_only_imports`: Count of static import descriptors (across all modules) that have an empty specifiers array.
- `avg_afferent_coupling`: Mean of afferent_coupling across all modules, rounded to output_precision.
- `avg_efferent_coupling`: Mean of efferent_coupling across all modules, rounded to output_precision.
