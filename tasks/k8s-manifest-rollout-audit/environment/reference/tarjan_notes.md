# Tarjan's SCC algorithm — notes for this task

The dependency graph is a directed graph on build-set chart names. Edges run from a chart to each of its (resolved) child requirement names that are also in the build set.

## Strongly-connected components

A strongly-connected component (SCC) is a maximal set of nodes where every node can reach every other node by following directed edges. Tarjan's classic algorithm computes all SCCs in linear time using a single DFS, an `index` counter, and a `lowlink` per node.

For the cycle output, two SCC shapes count as **cycle groups**:

- Any SCC with two or more members.
- A singleton SCC whose single member has a self-edge (`a -> a`).

A singleton SCC with no self-edge is **not** a cycle group.

## Condensation and topological order

The condensation of the graph is a DAG whose nodes are the SCCs. An edge `S1 -> S2` exists in the condensation iff some node in `S1` has an edge to some node in `S2` (and `S1 ≠ S2`).

The build order is a Kahn-style topological sort of the condensation:

1. Start with the set of SCCs with zero remaining indegree.
2. Emit them in order of their smallest member name (ASCII ascending). For each emitted SCC, decrement the indegree of all SCCs it points into and add any that drop to zero to the ready set.
3. Repeat until no more SCCs are ready.

Within an emitted SCC, members are listed ASCII-ascending.

## Determinism

To make the output byte-identical across runs:

- Iterate the build set in sorted order when seeding Tarjan.
- Sort each adjacency list before traversal.
- Tie-break the topo sort by `(smallest_member_name, scc_id)` so that recursion / iteration order does not leak into the output.
