# Radionuclide Decay Chain Activity Auditor

## Container Layout

| Path | Contents |
|------|----------|
| `/app/instruction.md` | Task description (injected by harness) |
| `/app/config/isotopes.json` | Isotope database with decay modes |
| `/app/config/policy.json` | Thresholds and severity definitions |
| `/app/config/facility.json` | Facility zones, detectors, shielding |
| `/app/samples/S*.json` | Per-sample initial activity compositions |
| `/app/measurements/det_*.csv` | Detector measurement time-series |
| `/app/docs/` | Mathematical and schema reference |
| `/app/decay_audit.cpp` | C++17 starter skeleton |
| `/app/Makefile` | Build rules for the C++ skeleton |

## Dependencies

- `g++` with C++17 support
- `nlohmann-json3-dev` (JSON for Modern C++)
- `python3` (alternative implementation language)

## Output

The auditor must produce a single file:

    /app/output/decay_audit.json

The stub skeleton creates this file with empty structures. See
`/app/docs/output_schema.md` for the full schema and
`/app/docs/decay_math.md` for the Bateman equation reference.

## Quick Test

```bash
make build && /usr/local/bin/decay_audit
cat /app/output/decay_audit.json
```
