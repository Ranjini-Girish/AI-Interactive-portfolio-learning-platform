# Detector Telemetry Calibration & Drift

End-to-end calibration, drift, and quality-finding pipeline over an
eight-channel detector dataset.

## Layout (inside the container)

```
/app
├── instruction.md                 task specification (read this first)
├── environment/
│   ├── Dockerfile                 container build
│   ├── Makefile                   builds calibrate.cpp -> /usr/local/bin/calibrate
│   ├── calibrate.cpp              C++17 starter skeleton (writes stub report)
│   └── README.md                  this file
└── detector/
    ├── policy.json                thresholds and tunables
    ├── channels.json              the 8 channels
    ├── calibration.json           reference (raw, true) pairs per channel
    ├── expected_signals.json      target signals
    ├── manifest.json              run list
    ├── exclusions.json            channels / runs / signals to exclude
    └── runs/
        └── run_NNN.tsv            per-run event traces
```

The pre-installed dependencies are `g++`, GNU `make`, `nlohmann-json3-dev`,
Python 3, and the standard Debian build chain.  You are free to use any of
these; nothing else is required.

## Output contract

Write the final report to `/app/detector/report.json`.  All the keys, sort
orders, rounding rules, and finding-evidence schemas are listed in
`/app/instruction.md`.

## Quick build smoke test

```
make -C /app/environment build && /usr/local/bin/calibrate
ls -l /app/detector/report.json
```

This will produce a stub report (only the top-level keys).  Replace
`calibrate.cpp` (or write your own Python script) to fill in the real
calibration, drift, signal, correlation, and finding logic.
