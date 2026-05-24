# Architecture

## Module Dependency Graph

```
main.rs
├── config.rs      (TOML config loading)
├── data.rs        (CSV parsing, design matrix construction)
├── validation.rs  (input validation)
├── regression.rs  (IRLS algorithm)
│   ├── matrix.rs  (linear algebra primitives)
│   ├── statistics.rs (MAD scale estimation)
│   └── weights.rs (Huber weight function)
├── covariance.rs  (sandwich covariance estimator)
│   └── matrix.rs
├── outliers.rs    (outlier detection)
├── diagnostics.rs (R² computation)
├── output.rs      (JSON report generation)
└── types.rs       (shared data structures)
```

## Data Flow

1. `config::load` reads `/app/config/analysis.toml`
2. `data::load_csv` reads `/app/data/sensors.csv`
3. `validation::validate` checks consistency
4. `data::build_design_matrix` constructs X (n×p) and y (n×1)
5. `regression::irls` runs the IRLS loop:
   - `statistics::mad` computes the MAD scale estimate
   - `weights::compute_weights` computes Huber weights
   - `matrix::solve` solves weighted least squares
6. `covariance::sandwich` computes robust standard errors
7. `outliers::detect` flags outlier observations
8. `diagnostics::r_squared_robust` computes goodness-of-fit
9. `output::build_report` + `output::write_json` produce the JSON report

## Matrix Storage

All matrices are stored as flat `Vec<f64>` in **row-major** order.
A matrix with `m` rows and `n` columns has element `(i, j)` at
index `i * n + j`.

## Error Handling

The pipeline uses `panic!` for unrecoverable errors (missing files,
malformed data). All numeric computations use `f64` throughout.
