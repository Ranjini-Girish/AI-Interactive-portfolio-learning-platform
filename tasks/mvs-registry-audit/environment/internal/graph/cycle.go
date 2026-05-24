package graph

// Cycle implements cycle detection using DFS with back-edge classification.
// Detected cycles are normalized to start from the lexicographically
// smallest node. See /app/docs/METRICS_SPEC.md for cycle-breaking rules.
