Build a Java 21 command-line analyzer for the synthetic Cargo workspace under `/app/workspace`. The Java 21 source lives under `/app/src`, including `/app/src/main.rs`; update it as needed. The analyzer must be compiled and runnable as `/app/build/incremental-cache-audit`, and each run must write `/app/output/cache_audit.json`.

All required verifier packages are already installed system-wide in the image; do not install packages at runtime.

The workspace model is stored in `/app/workspace/crates/*.crate`. Each file is a line-oriented record with `key=value` pairs. Values may contain comma-separated lists. Dependency entries have the form `crate_name:edge_kind:visibility`, where `edge_kind` is `normal`, `build`, or `dev`, and `visibility` is `public` or `private`.

The change log is `/app/workspace/changes.txt`. Non-comment lines have the form `path|change_kind|symbol`. Exact duplicate change lines count once and must be reported as duplicate input.

Produce a JSON object with these top-level keys:

`schema_version`, `summary`, `dirty_crates`, `clean_crates`, `build_plan`, `findings`, and `warnings`.

Required semantics:

- `schema_version` is `1`.
- A changed file belongs to the crate whose `public`, `private`, `build`, or `tests` list contains that path.
- Production dirty roots are non-test-only changes in crate-owned files.
- `api` and `feature` changes are surface changes and propagate transitively through reverse `normal` and `build` edges. They do not propagate through `dev` edges.
- `build_script` changes are surface changes for the owning crate and propagate transitively through reverse `normal` and `build` edges.
- Any change inside a `proc-macro` crate is a macro-expansion change and propagates transitively through reverse `normal` and `build` edges.
- `impl` changes dirty the owning crate. They propagate only to direct reverse `build` dependents, not through reverse `normal` or `dev` edges.
- `test_only` changes do not dirty production crates, but they should make the owning test crate appear in `summary.test_dirty_crates`.
- `summary.test_dirty_crates` also includes test crates reached through reverse `dev` edges from any production dirty crate.
- `dirty_crates` is sorted by crate name. Each entry must include `name`, sorted unique `reasons`, sorted unique `changed_symbols`, and `direct`.
- `clean_crates` is sorted by crate name.
- `build_plan.batches` is a list of sorted crate-name arrays. Dirty crates may appear only after every dirty dependency they require through `normal` or `build` edges. Clean dependencies do not appear in the plan.
- `build_plan.critical_path_ms` is the maximum sum of `build_ms` along dirty `normal` or `build` dependency paths ending at a dirty crate.
- `build_plan.critical_path` is one deterministic longest path. If paths tie, choose the lexicographically smallest full path.
- Findings are sorted by `(crate, code)`, then by `detail`.
- Warnings are sorted strings.

Use only the Java 21 standard library. The output JSON must be valid, deterministic, and based on the current contents of `/app/workspace`, not on hardcoded expected output.
