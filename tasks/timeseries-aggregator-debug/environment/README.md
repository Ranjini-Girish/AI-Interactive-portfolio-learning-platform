# Sensor Data Aggregation Tool

A C++ pipeline tool that processes time-series sensor data from CSV files,
aggregates readings into configurable time buckets, computes statistics,
detects threshold violations, and produces a JSON diagnostic report.

## Project layout

```
/app/
├── Makefile
├── src/
│   ├── main.cpp            # Entry point, config loading, orchestration
│   ├── types.hpp           # Shared data structures
│   ├── csv_parser.hpp/cpp  # CSV file reading and timestamp parsing
│   ├── json_parser.hpp/cpp # Minimal JSON parser for config
│   ├── aggregator.hpp/cpp  # Time-bucket grouping and stats
│   ├── detector.hpp/cpp    # Threshold violation detection
│   ├── reporter.hpp/cpp    # JSON report generation
│   └── utils.hpp/cpp       # Statistical helpers, SHA-256
├── data/                   # Sensor CSV files
├── config/
│   └── pipeline.json       # Processing configuration
└── output/
    └── report.json         # Generated report (output target)
```

## Building

```bash
make -C /app
```

## Running

```bash
/app/build/sensor_tool
```
