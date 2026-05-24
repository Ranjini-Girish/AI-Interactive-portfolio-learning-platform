# Capability Policy Audit Specification

The auditor scans workload profiles under `/app/data/workloads/` against `/app/config/policy.json` and writes `/app/output/capability_policy_audit.json`.

## Per-workload audit

For each workload JSON:

1. **Syscall allowlist** — For each `observed_syscalls` entry, if it is not in `tier_syscall_allowlist[risk_tier]`, emit `syscall_not_allowlisted` with evidence `{syscall, risk_tier}`.

2. **Required capabilities** — For each entry in `required_capabilities`, if it is absent from `observed_capabilities`, emit `missing_required_capability` with evidence `{capability}`.

3. **Forbidden capabilities** — For each entry in `forbidden_capabilities`, if it is present in `observed_capabilities`, emit `forbidden_capability_present` with evidence `{capability}`.

4. **effective_risk_score** — Among observed syscalls that are allowlisted for the tier, take the **maximum** `syscall_risk_weights[syscall]` (default weight 1). If none allowlisted, score is 0.

5. **Per-workload integrity lines** — One line per observed syscall (all observed, not only allowlisted): `workload_id|syscall|risk_weight`. Order syscalls by `(policy_syscall_order index ASC, syscall name ASC)` where unknown syscalls sort after known ones (index 999).

## Global ordering

- **workload_audits** — Sort by `(risk_tier_rank ASC, workload_id ASC)`.
- **findings** — Sort by `(severity_rank ASC, finding_type ASC, workload_id ASC)`.

## Summary

- **avg_effective_risk_score** — Harmonic mean of positive `effective_risk_score` values across workloads, rounded to 4 decimal places.
- **integrity_hash** — SHA-256 hex of all per-workload integrity lines concatenated in `workload_audits` order, joined by `\n` (no trailing newline on the body).

## source_hashes

Include `config/policy.json` and every `data/workloads/*.json`. Keys sorted alphabetically. Hash canonical bytes: CRLF→LF, strip one trailing newline if present.
