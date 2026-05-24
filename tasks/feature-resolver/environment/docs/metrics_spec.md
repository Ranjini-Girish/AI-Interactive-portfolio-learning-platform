# Metrics Specification

All metrics are computed on the **resolved** dependency graph — that is,
the graph produced after feature resolution and optional-dep activation.

## Depth (longest path from root)

Depth is the length of the **longest** path from the workspace root to
a given crate, measured in edges. The root has depth 0.

When cycles exist (see Cycle Detection below), all members of a
strongly connected component share the **same** depth. To compute depth:

1. Run Tarjan's algorithm to find all SCCs.
2. Build a **condensed DAG** by collapsing each SCC into a single node.
   The representative of an SCC is the **alphabetically first** member.
3. Compute longest-path distances on the condensed DAG from the root
   node (which is in its own SCC since it has no incoming edges).
4. Every member of an SCC gets the depth of that SCC's condensed node.

Unreachable crates have `depth: null`.

## Coupling

For each reachable crate:

- **fan_in** (Ca): the number of other reachable crates that depend on it
  (number of incoming edges in the resolved graph).
- **fan_out** (Ce): the number of distinct crates it depends on (number
  of outgoing edges in the resolved graph).
- **instability**: Ce / (Ca + Ce). If both Ca and Ce are 0, instability
  is `null`.

Round instability to `output_precision` decimal places.

## Active Size

The active size of a crate accounts for feature-dependent code:

    active_size = base_size_bytes × (1.0 + Σ weight_i)

where the sum runs over all **active** features that have an entry in
`feature_size_weights`. Features without an entry contribute 0.
Round to `output_precision` decimal places.

## Layer Classification

Every reachable crate is classified into exactly one layer:

| Layer       | Condition                                         |
|-------------|---------------------------------------------------|
| `entry`     | The workspace root crate (depth 0).               |
| `leaf`      | fan_out == 0 (no outgoing resolved dependencies). |
| `internal`  | All other reachable crates.                       |

Unreachable crates get `layer: "unreachable"`.

## Cycle Detection

Use **Tarjan's strongly connected components** algorithm on the resolved
directed graph. Any SCC with more than one member constitutes a
dependency cycle.

Report:

- `cycle_count`: the number of SCCs with size > 1.
- `cycles`: a list of cycles sorted by the alphabetically first member.
  Each cycle is a sorted list of crate names within that SCC.
- `is_acyclic`: true if cycle_count == 0.

## Build Order

Compute a valid **build order** (dependencies before dependents) using
Kahn's algorithm on the **condensed DAG** (the reversed edge direction:
process nodes whose dependencies are all built).

1. Start with nodes that have in-degree 0 in the original condensed
   DAG — these are the leaf dependencies that nothing further depends on.

   Actually: in the dependency graph, edges go from dependent → dependency.
   For build order we need dependencies first. So run Kahn's on the
   **transpose** of the condensed DAG (edges reversed: dependency → dependent).
   Nodes with in-degree 0 in the transpose = nodes with **out-degree 0**
   in the original condensed DAG = leaf crates.

2. When multiple nodes have the same in-degree-zero status in the same
   round, process them by **(build_priority ASC, depth DESC, name ASC)**
   of the SCC representative. `build_priority` is defined in each
   crate's JSON. For an SCC with multiple members, use the **minimum**
   `build_priority` among all members as the SCC's priority, and the
   SCC's depth value (from the longest-path calculation) as the depth.
   Higher-depth SCCs are built first at the same priority, because they
   are farther from the root and more likely to be foundational.

3. When emitting members of a multi-member SCC, list them in
   **alphabetical order**, adjacent in the build order.

The build order includes **all** crates in the workspace (reachable and
unreachable). Unreachable crates (which have no resolved edges) appear
as isolated nodes and are emitted in their alphabetical position among
other zero-in-degree nodes.
