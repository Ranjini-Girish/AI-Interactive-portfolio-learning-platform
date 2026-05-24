# Policy Rules Reference

Policy file: `/app/config/policy.json`.

- **risk_tiers** — Maps tier name to rank (lower rank = lower risk).
- **tier_syscall_allowlist** — Syscalls permitted per tier.
- **syscall_risk_weights** — Integer weight per syscall name.
- **policy_syscall_order** — Canonical syscall ordering for integrity lines.
- **finding_severity** / **severity_ranks** — Severity string and sort rank per finding type.

Finding types: `syscall_not_allowlisted`, `missing_required_capability`, `forbidden_capability_present`.
