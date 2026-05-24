# Metrics Reference

## Per-Service Statistics

For each service, the metrics stage computes:

- **span_count**: Total number of spans for this service.
- **error_count**: Number of spans with `status === "error"` or `level === "error"`.
- **error_rate**: `error_count / span_count`, rounded to `config.output.precision` decimal places.
- **latency**: Object containing latency statistics computed from the service's span durations.

## Latency Statistics

All latency values are in milliseconds.

- **mean**: Arithmetic mean of all span durations for the service.
- **min**: Minimum span duration.
- **max**: Maximum span duration.
- **Percentiles** (p50, p90, p95, p99): Computed using the nearest-rank method.

### Percentile Calculation (Nearest-Rank Method)

Given a sorted array of N values (sorted in ascending **numeric** order):

1. Compute the rank: `rank = ceil(p / 100 * N)`
2. The percentile value is the element at index `rank - 1` (0-based).

The array MUST be sorted numerically (ascending), not lexicographically. For example, `[9, 80, 100]` sorted numerically is `[9, 80, 100]`, but lexicographic sort would give `["100", "80", "9"]` which is incorrect.

## Precision

All floating-point metrics are rounded to `config.output.precision` decimal places using `toFixed()` and then parsed back to a number with `parseFloat()`.
