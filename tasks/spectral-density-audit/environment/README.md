# Spectral Density Estimation Tool

This environment contains time-series signal data and configuration for a power spectral density analysis pipeline.

## Directory Layout

```
/app/
├── data/
│   ├── config.json           # Analysis configuration
│   └── signals/              # Input signal files (signal_01.json .. signal_08.json)
├── docs/                     # Algorithm specifications
│   ├── dft_reference.md
│   ├── window_functions.md
│   ├── welch_method.md
│   ├── peak_detection.md
│   └── output_format.md
├── build/                    # Compiled binaries go here
└── output/                   # Analysis output goes here
```

## Tools Available

- `g++` (C++17)
- `make`
- `python3`
