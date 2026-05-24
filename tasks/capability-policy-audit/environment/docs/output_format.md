# Output Format

Write `/app/output/capability_policy_audit.json` with 2-space indentation and a trailing newline.

## Top-level keys

`schema_version` (always `1`), `source_hashes`, `workload_audits`, `findings`, `summary`.

## workload_audits

Each entry: `workload_id`, `risk_tier`, `risk_tier_rank`, `syscall_count`, `effective_risk_score`, `integrity_lines`.

## findings

Each entry: `finding_type`, `severity`, `severity_rank`, `workload_id`, `evidence` (object).

## summary

`workload_count`, `total_findings`, `findings_by_type`, `findings_by_severity`, `avg_effective_risk_score`, `integrity_hash`.

`findings_by_severity` must include keys `critical`, `high`, `medium`, `low`, `info` (zero if none).
