We have six distributed saga traces under `/app/data/sagas/` that need a deterministic replay audit written to `/app/output/saga_replay_audit.json`. The TypeScript on Node 22 crate at `/app` compiles but the replay engine returns wrong metrics and findings.

Read `/app/docs/replay_spec.md` and `/app/docs/output_format.md` for the authoritative rules. Policy severities are in `/app/config/policy.json`. Do not modify anything under `/app/data/` or `/app/config/`.

You must fix the TypeScript on Node 22 implementation (not rewrite in another language), then `cargo build --release`, copy the binary to `/app/build/saga-replay-audit`, and run it. Output JSON uses 2-space indentation with a trailing newline.
