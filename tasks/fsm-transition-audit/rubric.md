Agent reads /app/docs/replay_spec.md and /app/config/policy.json before editing Rust replay logic, +2
Agent inspects workflow logs under /app/data/workflows/ and FSM defs under /app/data/fsm_defs/ before implementing fixes, +1
Agent fixes transition ordering to sort by (sequence ASC, logged_at ASC) instead of logged_at alone in src/replay.rs, +3
Agent applies terminal_reopened check before illegal_transition when current state is terminal, +3
Agent preserves duplicate transition_id skipping in sorted walk order with duplicate_transition_skipped findings, +2
Agent detects timestamp_regression when a kept transition logged_at is strictly less than the previous kept transition, +2
Agent computes per-workflow avg_dwell_ms as harmonic mean of positive duration_ms values, +3
Agent builds integrity_hash from replay-order lines without lexicographic transition_id sorting, +3
Agent computes source_hashes with CRLF-to-LF normalization and strips one trailing newline before SHA-256, +2
Agent compiles with cargo build --release and installs ELF binary at /app/build/fsm-transition-audit, +2
Agent runs the binary to write /app/output/fsm_audit_report.json with 2-space indent and trailing newline, +2
Agent modifies or overwrites any file under /app/data/ or /app/config/, -5
Agent rewrites the auditor in Python, Node, or shell JSON templating instead of fixing the Rust crate, -5
Agent hardcodes fsm_audit_report.json or copies a frozen golden report without replaying workflows, -5
Agent leaves replay sorted by logged_at only causing wrong dedup order and missed timestamp regressions, -3
Agent uses arithmetic mean for dwell times instead of the required harmonic mean, -3
Agent sorts integrity hash lines by transition_id instead of replay order within each workflow, -3
Agent checks illegal_transition before terminal_reopened so live-state reopen is misclassified, -3
Agent repeats the same failing cargo build or binary run three or more times without substantive source changes, -1
Agent attempts runtime package downloads (cargo install, apt-get, curl, wget) inside the container, -2
