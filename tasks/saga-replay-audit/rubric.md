Agent reads /app/docs/replay_spec.md and /app/docs/output_format.md before editing Rust replay logic, +2
Agent inspects saga JSON files under /app/data/sagas/ and policy at /app/config/policy.json before implementing fixes, +1
Agent fixes event ordering to sort by (sequence ASC, timestamp_ms ASC) instead of timestamp_ms alone in src/replay.rs, +3
Agent preserves duplicate event_id skipping in sorted walk order and emits duplicate_event_skipped findings, +2
Agent detects out_of_order_timestamp when a kept event timestamp_ms is strictly less than the previous kept event, +2
Agent validates orphan_parent when parent_event_id is not present among kept events of the same saga, +2
Agent tracks step lifecycle (started, completed, compensated) and emits stalled_step for steps left in started state, +3
Agent enforces compensation_order_violation when compensated events are not strictly decreasing by sequence in replay order, +2
Agent computes per-saga avg_step_latency_ms as harmonic mean of positive duration_ms on completed kept events, +3
Agent builds integrity_hash from replay-order lines saga_id|event_id|sequence|status without lexicographic event_id sorting, +3
Agent computes source_hashes with CRLF-to-LF normalization and strips one trailing newline before SHA-256, +2
Agent compiles with cargo build --release and installs the ELF binary at /app/build/saga-replay-audit, +2
Agent runs the compiled auditor to write /app/output/saga_replay_audit.json with 2-space indentation and trailing newline, +2
Agent modifies or overwrites any file under /app/data/ or /app/config/, -5
Agent rewrites the auditor in Python, Node, or shell-only JSON templating instead of fixing the Rust crate, -5
Agent hardcodes /app/output/saga_replay_audit.json or copies a frozen golden report without replaying sagas, -5
Agent leaves replay sorted by timestamp_ms only causing wrong dedup order and incorrect timestamp findings, -3
Agent uses arithmetic mean for step or saga latency instead of the harmonic mean required by the specification, -3
Agent sorts integrity hash lines by event_id lexicographically instead of replay order within each saga, -3
Agent edits src/replay.rs or src/report.rs without consulting replay_spec.md for ordering and hash rules, -3
Agent repeats the same failing cargo build or saga-replay-audit run three or more times without substantive source changes, -1
Agent attempts runtime package downloads (cargo install, apt-get, curl, wget) inside the container, -2
