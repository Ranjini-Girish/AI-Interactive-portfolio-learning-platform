# Merkle DAG Validator

A Rust tool that validates the integrity of a content-addressed Merkle DAG.

## Building

```bash
cargo build --release
```

## Running

```bash
./target/release/merkle-dag-validator
```

Reads input from `/app/data/` and writes output to `/app/output/validation_report.json`.

## Documentation

- `docs/algorithm.md` -- High-level algorithm overview
- `docs/hash_spec.md` -- Hash computation specification
- `docs/output_schema.md` -- Output JSON format
- `docs/validation_rules.md` -- Validation logic details
- `docs/repair_model.md` -- Repair cost computation
- `docs/depth_rules.md` -- Depth computation rules
