Our deploy manifest audit pipeline under `/app` reconciles release manifests against the artifact registry, verifies checksum sidecars, merges environment overlays, and writes `/app/output/audit_report.json`. Run it with `/app/run_audit.sh`.

The pipeline is producing wrong numbers: deployment-to-artifact matching fails for mixed-case and separator variants in IDs, effective deploy duration is understated, size drift risk levels are off, overlay conflict detection does not follow policy layer order, the integrity chain hash does not match verified links in deployment order, and the median duration in the summary is wrong. Deployment rows in the report may also be sorted incorrectly.

Fix the bugs in the existing TypeScript on Node 22 modules under `/app/lib/`. Do not modify anything under `/app/data/` or `/app/config/`.

The report must be JSON with two-space indentation and a trailing newline. Top-level keys: `summary`, `deployments`, `checksum_audit`, `environment_overlay`, `integrity_chain`. Each deployment row includes `deployment_id`, `environment`, `artifact_sha256`, `declared_size_bytes`, `effective_duration_sec` (one decimal), and `risk_level` (`low`, `medium`, or `high`). Risk uses fractional drift thresholds from `/app/config/policy.json`. The integrity chain covers checksum-verified matched deployments only, ordered by `deployment_id` ascending. See `/app/docs/output_format.md` for field definitions.

You must keep the solution in TypeScript on Node 22 using this shell codebase.
