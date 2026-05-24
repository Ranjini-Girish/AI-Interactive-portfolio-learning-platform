A TypeScript on Node 22 tool must be implemented at `/app/src/index.js` so that `TypeScript on Node 22 /app/src/index.js` produces `/app/output/audit_report.json` — a license compliance audit of three software projects against the organizational policy in `/app/config/policy.json`.

Inputs:
- `data/packages/` — one JSON file per package (`name`, `version`, `license`, optional `linking_type`, `dependencies`)
- `data/projects/` — one JSON file per project (`project_id`, `license`, `direct_dependencies`)

For each project, resolve the full transitive dependency tree (keeping only the shallowest occurrence of each package), evaluate every dependency's effective license against the policy, detect violations (banned, restricted, and copyleft propagation), and compute a weighted risk score. Write a single `audit_report.json` containing a `metadata` block, a `projects` array, and a `summary` block.

Full license expression rules (SPDX OR/AND, copyleft propagation, LGPL exemption, waivers), the complete output schema, and risk scoring formula are in `/app/docs/`.
