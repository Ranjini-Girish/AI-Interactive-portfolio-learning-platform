# Edge Cases & Special Handling

## Empty or Minimal Streams

When a stream has fewer valid observations than `min_observations`:
- Generate an `insufficient_data` finding
- Still compute `basic_stats` (with nulls where needed)
- Skip all other computations (percentiles, EMA, rolling, outliers,
  gaps, trend, change_points, stale)

When valid_count is 0: mean, variance, std_dev, min, max are all null.
When valid_count is 1: population_variance is 0.0, sample_variance is
null (division by zero with N-1=0). std_dev is 0.0.

## Constant Streams

When all valid values are identical:
- variance = 0, std_dev = 0
- MAD = 0
- All percentiles equal the constant value
- EMA is the constant value throughout
- For outlier detection with MAD=0: if a value differs from the median
  by more than epsilon, its z-score is infinity — serialize as `null`
  in JSON (outlier). If it equals the median within epsilon, z-score
  is 0 (not outlier).
- Trend: slope = 0, intercept = the constant, r_squared = null
  (because wss_total = 0)

## MAD = 0 with Non-Constant Data

This occurs when more than half the values are identical but some
differ. The median of the absolute deviations can be 0 even when the
data is not fully constant. In this case, any value differing from the
median by more than epsilon produces a z-score of infinity. Since JSON
cannot represent infinity, infinite z-score values must be serialized
as `null` in the output.

## Population vs Sample Variance

The config `variance_type` controls what appears in `basic_stats`:
- `"population"` → `variance` uses denominator N, `std_dev = sqrt(variance)`
- `"sample"` → `variance` uses denominator N-1

The field `sample_variance` is ALWAYS reported (using N-1 denominator)
regardless of `variance_type`. This is for informational purposes.

Rolling statistics ALWAYS use population variance/std_dev within
each window, regardless of the global variance_type setting.

## Percentile Edge Cases

For the exclusive (R-6) method with very small N:
- N=1: all percentiles equal the single value
- N=2: h = 3×p. For p=0.05, h=0.15 < 1 → return min. For p=0.95,
  h=2.85 > 2 → return max.

When computing the index h = (N+1)×p, clamp to [1, N] before
interpolating. The exclusive method cannot produce values outside the
data range for p in (0,1).

## EMA with Null Values

When an observation is null:
- The EMA state carries forward: ema_state remains ema_state
  (no update)
- The output at that position is null
- The next valid observation uses the carried-forward state

The first non-null observation initializes the EMA state.

## CUSUM Warmup

The warmup period uses the first `cusum_warmup_count` **valid**
observations to compute the target mean. If fewer valid observations
exist in the warmup window, use however many are available (but if
zero, skip CUSUM entirely).

CUSUM scanning starts at the observation AFTER the warmup period ends.
The warmup observations themselves are never flagged as change points.

## Rolling Window at Boundaries

The centered window `[i - W÷2, i + W÷2]` is clipped to `[0, N-1]`.
This means:
- First few positions have smaller-than-full windows
- Last few positions also have smaller windows
- If the clipped window has fewer valid values than
  `rolling_min_window`, output null at that position

## Stale Data and Floating-Point Comparison

Two consecutive values are "identical" if `|v[i] - v[i-1]| < epsilon`.
A stale run extends as long as each consecutive pair satisfies this.

## Gap Analysis

Gaps are computed from the raw timestamp sequence (including null
observations). A gap between observation i and i+1 exists when
`timestamp[i+1] - timestamp[i] > max_gap_seconds`. Only gaps with
duration ≥ min_gap_duration generate findings.

## Finding Sort Keys

For findings referencing a specific observation index:
sort_key = index (integer)

For gap findings: sort_key = start_timestamp
For stale findings: sort_key = start_index
For insufficient_data: sort_key = 0

When two findings share the same (severity_rank, finding_type, sort_key),
they are ordered by stream_id in the global list.

## Findings by Severity — Zero Counts

The `findings_by_severity` summary must include ALL five severity
levels: `critical`, `high`, `medium`, `low`, `info`. Levels with no
findings must appear with count 0. This is a strict structural
requirement.
