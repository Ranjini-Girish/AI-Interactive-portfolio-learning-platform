# Output Schema: pipeline_audit.json

Write to `/app/output/pipeline_audit.json`.

## Top-Level Structure

```json
{
  "schema_version": 1,
  "summary": { ... },
  "source_sha256": { ... },
  "stream_audits": [ ... ],
  "findings": [ ... ]
}
```

## `summary`

| Field                  | Type   | Description                                 |
|------------------------|--------|---------------------------------------------|
| `total_streams`        | int    | Number of streams processed                 |
| `total_observations`   | int    | Sum of observation counts across all streams|
| `total_findings`       | int    | Total findings across all streams           |
| `findings_by_type`     | object | `{ finding_type: count }` sorted by key     |
| `findings_by_severity` | object | `{ severity: count }` for each of critical/high/medium/low/info (always present, 0 if none) |

## `source_sha256`

Object mapping relative paths (from `/app/`) of every file under
`config/`, `streams/`, and `pipelines/` to their SHA-256 hex digest.
Sorted by key. Forward-slash path separators.

## `stream_audits`

Array sorted by `stream_id`. Each object contains whichever analyses
were requested by the corresponding pipeline file.

### Required fields in every stream audit

| Field       | Type   | Description             |
|-------------|--------|-------------------------|
| `stream_id` | string | Stream identifier       |
| `findings`  | array  | Per-stream findings (empty array `[]` if none) |

### `basic_stats` (when requested)

| Field               | Type       | Description                     |
|---------------------|------------|---------------------------------|
| `count`             | int        | Total observations (incl. null) |
| `valid_count`       | int        | Non-null observations           |
| `null_count`        | int        | Null observations               |
| `mean`              | float/null | Arithmetic mean of valid values |
| `variance`          | float/null | Per config variance_type        |
| `std_dev`           | float/null | sqrt(variance)                  |
| `sample_variance`   | float/null | Always the N-1 denominator      |
| `min`               | float/null | Minimum valid value             |
| `max`               | float/null | Maximum valid value             |

When valid_count is 0, all numeric fields are null.
When valid_count is 1, sample_variance is null.

### `percentiles` (when requested)

Object mapping percentile labels to values:

```json
{"p5": 1.23, "p25": 4.56, "p50": 7.89, "p75": 10.12, "p95": 13.45}
```

Uses the exclusive (R-6) interpolation method.

### `ema` (when requested)

Array of EMA values, same length as the observations array. Null
entries where the input observation was null (EMA carries forward
internally but output is null at those positions).

### `rolling_stats` (when requested)

| Field          | Type  | Description                              |
|----------------|-------|------------------------------------------|
| `rolling_mean` | array | Rolling mean, same length as observations|
| `rolling_std`  | array | Rolling pop. std dev, same length        |

Null entries where the effective window is too small or NaN propagation
applies.

### `outliers` (when requested)

| Field    | Type       | Description                         |
|----------|------------|-------------------------------------|
| `median` | float      | Median of valid observations        |
| `mad`    | float      | Median Absolute Deviation           |
| `points` | array      | Array of outlier objects             |

Each outlier object:

```json
{"index": 18, "value": 200.0, "z_score": 673.13, "finding_type": "extreme_outlier"}
```

### `gaps` (when requested)

Array of gap objects (only gaps meeting min_gap_duration):

```json
{"start_timestamp": 1000300, "end_timestamp": 1000900, "duration": 600}
```

### `stale_runs` (when requested)

Array of stale run objects (only runs meeting stale_count threshold):

```json
{"start_index": 12, "end_index": 19, "run_length": 8, "value": 1500.0}
```

### `change_points` (when requested)

Array of change point objects:

```json
{"index": 22, "timestamp": 1001320, "direction": "up", "cusum_value": 15.82}
```

### `trend` (when requested)

| Field       | Type       | Description                    |
|-------------|------------|--------------------------------|
| `slope`     | float      | Weighted least squares slope   |
| `intercept` | float      | Weighted least squares intercept|
| `r_squared` | float/null | Coefficient of determination   |

### `findings`

Per-stream findings sorted by
`(severity_rank, finding_type, sort_key)` where sort_key is the
observation index or start_timestamp depending on the finding type.

Each finding object:

| Field          | Type        | Description                              |
|----------------|-------------|------------------------------------------|
| `finding_type` | string      | Type identifier                          |
| `severity`     | string      | Severity level from config               |
| `stream_id`    | string      | Stream containing the finding            |
| `evidence`     | object      | Supporting data specific to finding type |

#### Evidence by finding type

| Finding type         | Evidence fields                                        |
|----------------------|--------------------------------------------------------|
| `extreme_outlier`    | `index`, `value`, `z_score`, `median`, `mad`           |
| `outlier`            | `index`, `value`, `z_score`, `median`, `mad`           |
| `change_point`       | `index`, `timestamp`, `direction`, `cusum_value`       |
| `data_gap`           | `start_timestamp`, `end_timestamp`, `duration`         |
| `stale_data`         | `start_index`, `end_index`, `run_length`, `value`      |
| `insufficient_data`  | `valid_count`, `min_required`                          |

## Global `findings`

Aggregation of all per-stream findings, sorted by
`(severity_rank, finding_type, stream_id, sort_key)`.

All floating-point values rounded to `output_decimals` decimal places
(from `pipeline.json`).

JSON output: `indent=2`, trailing newline.
