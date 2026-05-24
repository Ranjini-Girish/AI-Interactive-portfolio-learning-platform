# Crate Audit Resolver

A Rust program that resolves semantic version constraints for a simulated
crate registry, computes dependency metrics, and produces an audit report.

## Input

- `data/manifest.json` — root workspace manifest with direct dependencies
- `data/registry/*.json` — one file per crate with version history
- `data/advisories.json` — security advisories to match against resolved crates

## Output

- `output/resolver_report.json` — structured JSON report

## Building

```bash
cargo build --release
./target/release/crate-audit
```

## Documentation

- `docs/resolution_algorithm.md` — resolution algorithm specification
- `docs/output_format.md` — output JSON schema
