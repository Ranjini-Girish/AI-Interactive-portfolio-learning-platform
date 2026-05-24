# Rubric: rust-merkle-dag-validator

## Positive Criteria

Agent identifies that the hash computation in hasher.rs sorts children by node_id instead of by their computed hash value as specified in hash_spec.md and hash_params.json, +5
Agent fixes the sort comparator in hasher.rs from a.0.cmp(b.0) to a.1.cmp(b.1) to sort by hash value, +3
Agent identifies that compute_depths in metrics.rs uses BFS which gives shortest-path distance instead of longest-path depth required by depth_rules.md, +5
Agent replaces the BFS depth computation with topological relaxation that updates depths to the maximum path length, +3
Agent identifies that repair cost computation in metrics.rs uses sum of children costs instead of max as specified in repair_model.md for the parallel repair model, +5
Agent fixes the repair cost aggregation from .sum() to .max().unwrap_or(0) in metrics.rs, +2
Agent identifies that validator.rs skips validation for nodes with fewer than 2 children contradicting validation_rules.md which requires all nodes be validated, +5
Agent removes the children.len() < 2 guard clause in validator.rs to validate all nodes including leaves and single-child nodes, +2
Agent identifies that the findings sort order in report.rs uses depth ascending instead of depth descending as specified in output_schema.md and algorithm.md, +3
Agent fixes the sort comparator in report.rs from a.depth.cmp(&b.depth) to b.depth.cmp(&a.depth), +2

## Negative Criteria

Agent modifies input data files under /app/data/ which must remain unchanged, -5
Agent rewrites the entire Rust codebase in Python or another language instead of fixing the Rust implementation, -5
Agent deletes or empties test files or modifies the test harness rather than fixing the source code, -5
Agent introduces compilation errors that prevent cargo build --release from succeeding, -3
Agent hardcodes expected output values without actually fixing the underlying algorithmic bugs, -3
Agent only fixes one or two bugs and declares the task complete without verifying all tests pass, -1
