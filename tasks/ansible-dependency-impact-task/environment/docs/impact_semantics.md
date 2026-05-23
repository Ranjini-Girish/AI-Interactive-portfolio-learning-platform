# Dependency Impact, Cycles, and Remediation

Dependency relationships and topological analysis over the final build set are determined as follows:

## 1. Dependency Relationships
- For each module in the build set, resolve each of its registry `require` children.
- If the resolved child module is also in the build set, establish a directed dependency edge: `parentDependsOn -> child`.
- The list of resolved dependencies for each module is deduplicated and sorted ASCII ascending.

## 2. Cycles & SCC Groups
- Group the build-set modules by mutual reachability (Strongly Connected Components).
- **Cycle Group**: A cycle group is any component containing 2 or more modules, OR a single module that depends on itself (a self-loop in the dependency graph).
- `resolver_summary.cycle_group_count` counts all such cycle groups.
- `cycles` lists the membership of each cycle group. Sort each member list ASCII ascending. Sort the outer list of groups by the ASCII minimum member name.

## 3. Build Order (Topological Sort)
- Project the dependency graph onto the SCC groups (condensation graph).
- Perform a topological sort over the groups: if group *A* depends on group *B* (and they are different), *B* must precede *A* in the order.
- **Canonical Ordering**: To ensure determinism when multiple topological orders satisfy the graph, resolve ties at each step by choosing the group whose minimum member name is lexicographically smallest in ASCII.
- `build_order` is the final flat list of groups (each group's member list is sorted ASCII ascending).

## 4. Impact Analysis
- **Task Seed**: For each changed task ref (`<play_name>::<task_name>`), resolve all of its requirements from `task_dependency_map.json`. If a resolved module is in the build set, it is a task seed.
- **Impacted Modules**: The set of task seeds plus any build-set module that is directly or transitively reachable from any task seed.
- **Triggered By**: For each impacted module, `triggered_by` is the list of changed task refs that can reach it, sorted ASCII ascending.
- **Seed Modules List**: Output one row per `(task_ref, module_name)` seed pair that resolves to the build set. The `version` field is the final resolved version from the build set. Sort the list by `(task_ref, module)` ASCII ascending.

## 5. Remediation Plan (`remediation_plan.json`)
Construct the remediation plan steps from the `build_order`:
1. Loop through `build_order`. For each group/step, retain only the modules that belong to `impacted_modules`, preserving their order inside the step.
2. If a step's filtered module list is empty, drop the step entirely.
3. Re-index the surviving steps starting from `1`.
4. For each step, `triggered_by` is the union of `triggered_by` refs of all modules in that step, sorted ASCII ascending.
