# Anomaly Detection

## Method: Z-Score

Anomalous spans are detected using the z-score method. For each service with at least `config.anomaly.min_samples` spans, a z-score is computed for every span's latency.

## Formula

For a set of latency values within a service:

1. Compute the sample mean: `mean = sum(values) / N`
2. Compute the **sample** standard deviation (Bessel's correction):
   - `variance = sum((xi - mean)^2) / (N - 1)`
   - `stddev = sqrt(variance)`
3. For each span: `z_score = |latency - mean| / stddev`
4. A span is anomalous if `z_score > config.anomaly.threshold`.

**Important**: The denominator for variance is `N - 1` (sample standard deviation), not `N` (population standard deviation). This distinction matters for small sample sizes.

## Skipped Services

Services with fewer than `config.anomaly.min_samples` spans are skipped entirely. Services where the standard deviation is exactly zero are also skipped.

## Output

Anomalies are sorted by z-score in descending order. Each anomaly record includes: `span_id`, `trace_id`, `service`, `latency_ms`, `z_score`, and `threshold`.
