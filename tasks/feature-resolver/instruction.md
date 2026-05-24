Implement a Java 21 program that reads crate definitions from `/app/data/crates/`, workspace config from `/app/data/workspace.json`, and build config from `/app/data/config.json`. The program must resolve Cargo-style feature flags and produce a build plan at `/app/output/build_plan.json`. Do not modify any file under `/app/data/` or `/app/docs/`.

All computation rules are specified in four documents under `/app/docs/`:
- `resolution_spec.md` — feature resolution algorithm
- `metrics_spec.md` — depth, coupling, cycle, and build-order rules
- `findings_spec.md` — quality finding types, triggers, and sorting
- `output_format.md` — JSON schema and formatting requirements

These documents are the **sole authoritative source**. Read all four before writing code. A starter project exists at `/app/src/main.rs` with `Cargo.toml`. You may add any additional crate dependencies you need to `Cargo.toml`.

Compile with `cargo build --release`, copy the binary to `/app/build/feature-resolver`, and run it.
