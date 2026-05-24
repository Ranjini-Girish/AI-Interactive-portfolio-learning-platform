package graph

// Topo implements topological sort with cycle detection and breaking.
// Tie-breaking uses lexicographic ordering by package name.
// See /app/docs/METRICS_SPEC.md for the cycle-breaking algorithm.
