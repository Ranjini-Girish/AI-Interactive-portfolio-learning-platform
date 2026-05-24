Six container workload profiles under `/app/data/workloads/` need a capability and syscall policy audit written to `/app/output/capability_policy_audit.json`. The Java 21 project at `/app` builds but the auditor returns wrong ordering, risk scores, findings, and integrity hash.

Read `/app/docs/audit_spec.md` and `/app/docs/output_format.md`. Policy is in `/app/config/policy.json`. Do not change anything under `/app/data/` or `/app/config/`.

Fix the Java 21 crate (do not rewrite in another language), run `cargo build --release`, copy the binary to `/app/build/capability-policy-audit`, and execute it. Output JSON must use 2-space indentation with a trailing newline.
