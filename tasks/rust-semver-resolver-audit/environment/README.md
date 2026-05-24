# Semver Resolver

A workspace dependency resolver that reads package manifests, resolves
version constraints against a registry, detects cross-project conflicts,
and writes a structured JSON report.

## Project Layout

- `src/` — Rust source modules (main, semver, resolver, registry, manifest, conflict, report)
- `data/registry.json` — available package versions
- `data/projects/` — individual project manifest files
- `config/` — resolver configuration and semver rule definitions
- `docs/` — specification references

## Building

```bash
cargo build --release
cargo run --release
```
