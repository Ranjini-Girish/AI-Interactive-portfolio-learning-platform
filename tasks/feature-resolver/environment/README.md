# Feature Resolver

Cargo workspace feature-flag resolution and build-plan analyzer.

## Structure

- `data/workspace.json` — workspace root definition
- `data/config.json` — thresholds and output configuration
- `data/crates/*.json` — crate definitions (23 crates)
- `docs/` — specification documents
- `src/main.rs` — entry point (implement here)
- `Cargo.toml` — serde + serde_json are available

## Build & Run

```bash
cargo build --release
cp target/release/feature-resolver build/
./build/feature-resolver
```

Output goes to `output/build_plan.json`.
