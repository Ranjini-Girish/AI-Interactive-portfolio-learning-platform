# Rebuild Rules

## Dirty Target Detection
Given a list of changed files in `/app/data/changes.json`:

1. A target is **directly dirty** if any of its `sources` or `headers` entries appears in the changed files list. Matching is by exact string equality.
2. A target is **transitively dirty** if any target in its `depends_on` list (recursively, through the full dependency chain) is dirty.
3. A target that is neither directly nor transitively dirty is **clean**.

## Rebuild Order
Only dirty targets need rebuilding. The rebuild order is the subsequence of the full topological order containing only dirty targets. Clean targets are skipped entirely.

## Important
- A changed file that does not appear in any target's `sources` or `headers` is ignored.
- Transitive dirtiness propagates through the `depends_on` graph, not through file-level include analysis. If target A depends on target B, and B is dirty, then A is dirty regardless of whether A's source files actually include any of B's headers.
