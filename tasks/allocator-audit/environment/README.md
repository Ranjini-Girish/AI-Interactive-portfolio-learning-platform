# Allocator Audit Environment

This environment contains a memory allocator simulation task.

- `/app/data/pool_config.json` — Memory pool configuration
- `/app/data/traces/` — Allocation/deallocation trace files (trace_01 through trace_12)
- `/app/docs/` — Detailed specification documents
- `/app/src/main.rs` — Stub entry point (replace with your implementation)
- `/app/Cargo.toml` — Rust project manifest with serde/serde_json dependencies

Build with `cargo build --release` and place the binary at `/app/build/allocator`.
