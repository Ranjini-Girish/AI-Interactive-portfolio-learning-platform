# Ivy build lattice audit

Inputs live beside this file. Read `policy.json`, `pool_state.json`, `incidents.json`, and every `*.json` file directly under `modules/`. Ignore `ledger/`, `ancillary/`, and `anchors/` for semantics.

## Canonical JSON

Emit JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Module objects

Each module JSON has `module_id` (string), integer `build_cost`, and `prereqs` (array of strings naming prerequisite modules). `prereqs` must be sorted lexicographically in emitted `module_catalog.json` even if the source file order differs. A prerequisite edge points from prerequisite `p` to dependent `m` meaning `p` must appear before `m` in any linear build schedule.

## Cycle semantics

Treat the graph as directed using prerequisite edges. Identify every maximal strongly connected component that contains more than one distinct module id OR contains a directed cycle (equivalently: any component with size greater than one). The `cycle_members` output lists every `module_id` that participates in any such component, sorted ascending, deduplicated.

`linearizable` is true only when no directed cycle exists anywhere in the graph. When `linearizable` is false, `linear_order.json` must set `linear_order` to JSON `null`. When true, `linear_order` is an array listing every module exactly once in a valid topological order; ties among ready modules are broken by choosing the smallest ASCII `module_id`.

## Path weights

When `linearizable` is true, compute `path_weights` as a map from each `module_id` to the maximum sum of `build_cost` along any directed path that ends at that module, inclusive of all module costs on the path. When `linearizable` is false, emit `path_weights` as an empty object `{}`.

## Outputs

1. `module_catalog.json` with key `modules`: sorted array of `{build_cost, module_id, prereqs}` objects sorted by `module_id`.
2. `linear_order.json` with key `linear_order` as either an array of ids or `null`.
3. `cycle_members.json` with key `members` as the sorted array defined above (possibly empty).
4. `path_weights.json` with key `weights` mapping ids to integers, or `{}` when not linearizable (use an empty object for the entire file payload in that case: `{}` is acceptable only if the file is literally `{}` with newline - actually use `{"weights":{}}` for consistent top-level? SPEC says path_weights.json - use `{"weights":{}}` when cyclic else `{"weights":{...}}` for stable key

I'll set always `{"weights": map}` - when cyclic map empty.

5. `summary.json` with keys `cycle_member_count` (len members), `graph_label` (copy from `policy.graph_label`), `linearizable` (bool), `modules_total` (int).

## Tooling

`IBL_DATA_DIR` defaults `/app/ivybuild`, `IBL_AUDIT_DIR` defaults `/app/audit`. Create audit dir if missing; never mutate inputs.
