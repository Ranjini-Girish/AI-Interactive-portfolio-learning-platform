# Dependency License Compliance Auditor

Analyses npm-style package dependency trees for license policy compliance.

## Layout

- `data/packages/` — Package definition JSON files (name, version, license, deps)
- `data/projects/` — Project definition JSON files (id, license, direct deps)
- `config/policy.json` — License policy (allowed/restricted/banned, waivers)
- `docs/` — Algorithm specifications
- `src/` — Node.js source stubs

## Running

    node /app/src/index.js
