# Dependency Health Auditor

Analyze a Rust workspace for dependency resolution, coupling metrics, license compatibility, and health scoring.

## Layout

```
/app/
├── Cargo.toml
├── src/main.rs
├── data/
│   ├── workspace.json
│   ├── workspace/  (7 member manifests)
│   └── registry/   (16 crate registries)
├── docs/
│   ├── semver_spec.md
│   ├── resolution_spec.md
│   ├── metrics_spec.md
│   ├── license_spec.md
│   ├── health_spec.md
│   └── output_format.md
└── output/
```
