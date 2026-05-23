# Impact semantics

## Seed modules

`seed_modules` records exactly the workload-derived seeds, never `release.require` seeds. For each changed-workload ref in `(added ∪ removed ∪ modified)`, look up its entry in `workload_dependency_map.json`. For each valid mapped pair, run it through `resolve_pair`. If the resolved name is in the build set, emit `{workload_ref, chart, version}` where `chart` is the resolved name and `version` is `build_versions[chart]`. Skip pairs whose resolved name is not in the build set.

`workload_ref` is always the literal string `namespace::workload_name`. `release` is never a valid `workload_ref`.

Sort `seed_modules` by `(workload_ref, chart)`.

## Impacted charts

Starting from each seed chart, traverse the dependency edges in the build-set graph and collect every reachable chart (including the seed itself). Deduplicate. For each impacted chart, record:

- `name` — the chart name.
- `version` — its build-set version (`build_versions[chart]`).
- `triggered_by` — the ASCII-sorted list of every workload ref whose seeds reach this chart through the dependency graph.

Sort `impacted_charts` by `name`.

## Rollout plan

Take the `build_order` and, step by step, keep only charts that are in `impacted_charts`. Drop steps whose filtered chart list is empty. Re-index the surviving steps starting from 1, sequentially with no gaps. Within a step, preserve the order from the corresponding `build_order` step. Each step's `triggered_by` is the ASCII-sorted union of its remaining charts' `triggered_by` lists.
