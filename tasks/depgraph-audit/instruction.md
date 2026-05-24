Build a tool that processes module registry definitions, resolves dependency
graphs using Minimum Version Selection, and produces a comprehensive audit
report.

## What You Have

The container provides:

- **`/app/data/registry/module_*.json`** — Module definitions (15 files).
  Each contains a module path, available versions with their dependencies and
  licenses, and optionally retracted versions.

- **`/app/data/queries/query_*.json`** — Resolution queries (9 files).
  Each specifies a root module, requirements (module + minimum version),
  optional `replaces` and `excludes` directives, and a `project_license`.

- **`/app/data/vulnerabilities.json`** — Known vulnerability database with
  affected version ranges.

- **`/app/config/audit.json`** — Audit configuration: resolution algorithm
  settings, license compatibility matrix, finding severity mappings, and
  thresholds.

- **`/app/docs/`** — Detailed algorithm specifications, output schema, and
  edge-case documentation.

- **`/app/cmd/depaudit/main.go`** — Entry-point stub.

## What To Build

Implement the full audit tool. For each query:

1. **Resolve dependencies** using Minimum Version Selection (MVS) as specified
   in `docs/algorithms.md`. Handle excludes, replaces, and pre-release
   versions.

2. **Build a dependency tree** mapping each resolved module@version to its
   direct dependencies.

3. **Detect cycles** in the resolved graph. Report each cycle as a sorted
   list of module paths.

4. **Compute build order** using Kahn's algorithm with lexicographic
   tie-breaking. Exclude cyclic modules.

5. **Compute max depth** of the resolved dependency graph.

6. **Check vulnerabilities** using inclusive-min, exclusive-max range
   semantics.

7. **Check license compatibility** against the matrix in audit.json.

8. **Flag retracted versions** that were resolved.

9. **Compute SHA-256 hashes** of all input files under `config/`, `data/`,
   and `docs/`.

10. **Generate findings** with proper severity mappings and sorting.

## Output

Write the audit report to `/app/output/dependency_audit.json` following the
schema in `docs/output_schema.md`. Use 2-space indentation, sorted keys, and
a trailing newline.

Read the documentation in `/app/docs/` carefully before implementing.
