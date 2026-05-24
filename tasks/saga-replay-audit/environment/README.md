# Saga Replay Audit

Rust project under `/app` replays saga event logs and writes `/app/output/saga_replay_audit.json`.

- Input sagas: `/app/data/sagas/*.json` (6 files)
- Policy: `/app/config/policy.json`
- Specs: `/app/docs/replay_spec.md`, `/app/docs/output_format.md`

Build: `cargo build --release`. Run the `saga-replay-audit` binary from `/app`.
