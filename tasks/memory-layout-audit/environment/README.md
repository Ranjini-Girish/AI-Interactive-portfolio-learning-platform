# layout-auditor (stub)

Rust crate that should read JSON type definitions from `/app/data/types/`, consume `/app/config/platform.json`, and emit `/app/output/layout_report.json` describing modeled x86_64 memory layouts across `repr(C)`, `repr(Rust)` (field reorder per spec), `repr(packed)`, and `repr(align(N))`, plus enum and niche rules documented in `/app/docs/`.

Until implemented, `main.rs` writes a minimal empty report so the workspace builds inside the grading image.
