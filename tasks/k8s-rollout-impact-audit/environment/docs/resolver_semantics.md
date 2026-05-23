# Resolver semantics

A requirement pair `{name, version}` is **valid** only when `name` is a non-empty string and `version` is exactly `MAJOR.MINOR.PATCH` with non-negative integer parts. This validation runs uniformly on every entry in `charts.json`, every entry in `release.require` / `release.replace.from` / `release.replace.to` / `release.exclude`, every child `require` array, and every value in `workload_dependency_map.json`. Invalid rows are silently dropped at the point they are encountered.

## Registry

`charts.json` is a list of `(name, version, require?)` records. The first occurrence of a `(name, version)` pair wins; later duplicates are silently dropped, including their `require` arrays. For each name, the set of valid versions is sorted ascending by semver and de-duplicated; this sorted list is the bump table used during exclude resolution.

## Replace and exclude

`release.replace` is a list of `{from, to}` rules. The first valid `from` pair wins per `from` key; later rules with the same `from` are dropped. Replace is applied **exactly once** and **non-transitively**: if `A 1.0 -> B 1.0` and `B 1.0 -> C 1.0` are both rules, starting from `A 1.0` produces `B 1.0`, not `C 1.0`. A name that has already been added to `selected` is not re-replaced when its child requirements are expanded.

`release.exclude` is a set of `(name, version)` pairs. After applying replace, if the post-replace pair is in the exclude set, the resolver steps up the bump table for that name to the next strictly-greater version that is not also excluded. The bump can chain across multiple consecutive excludes. If no such version exists, record `<name>@<version>` (the post-replace pair) into `conflicts` and drop the requirement.

## Selection

Initialize the resolver with all valid pairs from `release.require` plus all valid mapped pairs from `workload_dependency_map.json` keyed by each changed-workload ref `namespace::workload_name` (over the union of added, removed, and modified). Push every initial pair through `resolve_pair` and update `selected[name]` to the maximum version seen.

Then iterate to fixpoint: for each currently-selected `(name, version)`, look up its registry record and for every child requirement run `resolve_pair` and update `selected`. If a selected `(name, version)` is not in the registry, record `<name>@<version>` into `missing` and skip its expansion. Stop when no `selected[name]` changes in a full pass.

## Build set and edges

The build set is every name in `selected` whose `(name, selected[name])` is in the registry **and** whose name is not `release.name`. Build versions are kept under `build_versions[name] = selected[name]`. `resolver_summary.selected_total` is the size of the build set.

For each build-set chart, resolve its child requirements through `resolve_pair` and keep only edges that land on another build-set member. Sort each adjacency list ASCII ascending and deduplicate.

## Cycles

Run Tarjan's SCC algorithm on the build-set graph. A cycle group is any SCC of size ≥ 2 OR a singleton SCC whose only member has a self-edge. Each cycle's members are sorted ASCII ascending; the outer `cycles` list is sorted by smallest member.

## Build order

The build order is the SCC-condensation topological sort. Every SCC becomes one step (sorted member list). Process SCCs in topological order; when multiple SCCs are simultaneously eligible (zero remaining indegree), emit them in order of their smallest member name. Dependencies of a step always appear in earlier steps. Members within a step preserve the sorted order from the SCC.
