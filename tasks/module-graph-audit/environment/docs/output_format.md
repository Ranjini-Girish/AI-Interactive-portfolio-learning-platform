# Output Format Specification

## File

Write the output to `/app/output/module_report.json`.

## JSON Structure

Use 2-space indentation with a trailing newline.

```json
{
  "config": { ... },
  "modules": [ ... ],
  "dependency_edges": [ ... ],
  "circular_dependencies": [ ... ],
  "tree_shaking": { ... },
  "summary": { ... }
}
```

## Top-Level Keys (in order)

1. **config**: Copy of the project configuration from project_config.json.
2. **modules**: Array of per-module analysis objects, sorted by module_id.
3. **dependency_edges**: Array of edge objects, sorted by (source, target, type).
4. **circular_dependencies**: Array of SCC objects, sorted by cycle_id.
5. **tree_shaking**: Tree-shaking analysis result object.
6. **summary**: Aggregate summary object.

## Sorting

- All arrays of strings are sorted lexicographically.
- Module arrays are sorted by module_id.
- Edge arrays are sorted by (source, target, type).
- Import/export descriptors within a module are sorted by source.

## Floating-Point Precision

Round all floating-point values to the number of decimal places specified by `output_precision` in the config (default: 6).

## Null Handling

Use JSON `null` for values that cannot be computed (e.g., instability when Ca + Ce = 0).
