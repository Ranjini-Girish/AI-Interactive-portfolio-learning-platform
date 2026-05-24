# Robust Regression Pipeline

A Rust implementation of robust linear regression using Iterative
Reweighted Least Squares (IRLS) with the Huber M-estimator.

## Usage

```bash
cargo build --release
./target/release/robust-regression
```

The program reads input data from `/app/data/sensors.csv` and
configuration from `/app/config/analysis.toml`, producing a JSON
report at `/app/output/analysis.json`.

## Project Structure

- `src/` — Rust source code (see `docs/ARCHITECTURE.md`)
- `data/` — Input sensor data
- `config/` — Analysis configuration
- `docs/` — Specification and algorithm documentation
- `output/` — Generated analysis results
