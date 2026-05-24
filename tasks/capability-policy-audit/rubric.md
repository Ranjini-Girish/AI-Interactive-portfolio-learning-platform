Agent reads /app/docs/audit_spec.md and /app/docs/output_format.md before editing Rust audit logic, +2
Agent inspects workload JSON under /app/data/workloads/ and policy at /app/config/policy.json before implementing fixes, +1
Agent flags syscall_not_allowlisted only for observed syscalls outside tier_syscall_allowlist, +2
Agent emits missing_required_capability when a required capability is absent from observed_capabilities, +2
Agent emits forbidden_capability_present when a forbidden capability appears in observed_capabilities, +3
Agent computes effective_risk_score as the maximum syscall_risk_weights among allowlisted observed syscalls, +3
Agent orders per-workload integrity lines by policy_syscall_order then syscall name, +3
Agent sorts workload_audits by (risk_tier_rank ASC, workload_id ASC), +2
Agent sorts findings by (severity_rank ASC, finding_type ASC, workload_id ASC), +2
Agent computes summary avg_effective_risk_score as harmonic mean of positive workload scores rounded to 4 decimals, +3
Agent builds integrity_hash from ordered integrity lines across sorted workload_audits without extra sorting, +2
Agent computes source_hashes with CRLF-to-LF normalization and strips one trailing newline before SHA-256, +2
Agent compiles with cargo build --release and installs ELF at /app/build/capability-policy-audit, +2
Agent runs the auditor to write /app/output/capability_policy_audit.json with 2-space indent and trailing newline, +2
Agent modifies or overwrites files under /app/data/ or /app/config/, -5
Agent rewrites the auditor in Python, Node, or shell-only JSON templating instead of fixing Rust, -5
Agent hardcodes /app/output/capability_policy_audit.json without running the Rust auditor on workload inputs, -5
Agent checks forbidden capabilities against required_capabilities instead of observed_capabilities, -3
Agent uses sum of syscall weights or includes non-allowlisted syscalls in effective_risk_score, -3
Agent sorts integrity hash syscalls lexicographically instead of policy_syscall_order, -3
Agent sorts workload_audits by workload_id only or findings by workload_id before severity, -3
Agent uses arithmetic mean for avg_effective_risk_score instead of harmonic mean, -3
Agent repeats the same failing cargo build or auditor run three or more times without substantive source changes, -1
Agent attempts runtime package downloads (cargo install, apt-get, curl, wget) inside the container, -2
