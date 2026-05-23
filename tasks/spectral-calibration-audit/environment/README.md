# Spectral Calibration Audit

End-to-end calibration, drift correction, and audit pipeline over a
multi-instrument optical-emission spectrum dataset.

## Layout (inside the container)

```
/app
├── instruction.md                 task specification (read this first)
├── environment/
│   ├── Dockerfile                 container build
│   ├── Makefile                   builds calibrate.cpp -> /usr/local/bin/calibrate
│   ├── calibrate.cpp              C++17 starter skeleton (writes stub outputs)
│   └── README.md                  this file
└── experiments/
    ├── manifest.json              run list with metadata overrides
    ├── config/
    │   ├── instruments.json       per-instrument defaults
    │   ├── batches.json           per-batch defaults
    │   └── calibrants.json        expected peaks and analysis windows
    └── spectra/
        └── rNNN.csv               per-run wavelength,intensity rows
```

The pre-installed dependencies are `g++`, GNU `make`,
`nlohmann-json3-dev`, Python 3, and the standard Debian build chain. You
are free to use any of these for your own scaffolding; the contract is a
C++17 implementation.

## Output contract

Write the three output files to `/app/output/`:

- `run_audit.json` -- per-run inclusion/exclusion summary
- `calibration_summary.json` -- per-(calibrant, instrument) statistics
  and the best run per calibrant
- `peak_table.csv` -- one row per included (run, peak)

All keys, sort orders, rounding rules, and schema details are listed in
`/app/instruction.md`. The binary must respect the `APP_ROOT` environment
variable for both inputs (`$APP_ROOT/experiments`) and outputs
(`$APP_ROOT/output`).

## Quick build smoke test

```
make -C /app/environment build && /usr/local/bin/calibrate
ls -l /app/output/
```

This produces stub output files only. A passing submission will typically
ship its own `/app/Makefile` that builds `/app/build/calibrate` from
sources under `/app/src/`. Replace `calibrate.cpp` (or write your own
file tree) to fill in the real baseline-correction, peak-fit,
drift-correction, and audit-emission logic.
