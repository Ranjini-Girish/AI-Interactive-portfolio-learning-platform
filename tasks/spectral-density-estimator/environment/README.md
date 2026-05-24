# Spectral Density Estimator

C++ pipeline for power spectral density estimation from sensor time-series data.

## Build

```bash
make          # or: cmake -B build && cmake --build build
```

## Run

```bash
./spectral_analyzer
```

Reads configuration from `/app/config/`, processes data from `/app/data/`,
and writes the analysis report to `/app/output/spectral_report.json`.

## Project structure

- `src/` — C++ source and headers
- `data/` — input time-series CSV and example output
- `config/` — analysis parameters (segment size, overlap, thresholds)
- `docs/` — spectral analysis and Welch's method reference
