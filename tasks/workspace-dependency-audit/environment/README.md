# JavaScript Workspace Dependency Auditor

Analyze a monorepo workspace containing 5 npm-style packages and produce a comprehensive dependency audit report.

## Environment

- **Registry**: `data/registry/` — 16 packages with multiple versions each (JSON)
- **Workspace**: `data/workspace/` — 5 packages (pkg-api, pkg-auth, pkg-cli, pkg-core, pkg-utils), each with `package.json` and `src/` directory
- **Policy**: `data/workspace/policy.json` — license rules, severity configuration, risk scoring parameters
- **Advisories**: `data/workspace/advisories.json` — known vulnerability database

## Documentation

- `docs/SEMVER_RULES.md` — version constraint semantics (caret, tilde, workspace protocol)
- `docs/ALGORITHM.md` — full resolution algorithm, metrics, finding generation
- `docs/OUTPUT_FORMAT.md` — JSON output schema and formatting rules

## Task

Write a script that:
1. Resolves all workspace package dependencies using the local registry
2. Builds a full transitive dependency graph with BFS depth computation
3. Detects workspace dependency cycles
4. Identifies phantom dependencies from source analysis
5. Evaluates license compatibility per policy rules
6. Matches resolved versions against security advisories
7. Performs hoisting analysis
8. Computes summary metrics (harmonic mean avg_depth, geometric mean risk)

Write the result to `/app/output/workspace_audit.json`.

Node.js is available in the environment. Read the docs carefully — the semver caret operator has special behavior for 0.x versions.
