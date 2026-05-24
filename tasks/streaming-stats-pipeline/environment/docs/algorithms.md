# Statistical Algorithm Specifications

## Basic Statistics

For a stream of N valid (non-null) observations `x₁, x₂, …, xₙ`:

    mean = (Σ xᵢ) / N

    population_variance = Σ(xᵢ − mean)² / N

    sample_variance = Σ(xᵢ − mean)² / (N − 1)

    std_dev = sqrt(population_variance)

The `variance_type` field in `pipeline.json` controls which variance
formula is reported in `basic_stats.variance` and which square root
appears as `std_dev`. When `variance_type` is `"population"`, both use
the population formula (denominator N). When `"sample"`, both use
sample (denominator N−1). When N < 2 and sample variance is needed,
it is `null`.

Also report `min`, `max`, `count` (total observations including nulls),
`valid_count` (non-null observations), and `null_count`.

## Percentiles — Exclusive Method (R-6)

Compute percentiles from the sorted array of **valid** values only.

Given N sorted values `s[1], s[2], …, s[N]` (1-indexed) and percentile
level p ∈ (0, 1):

    h = (N + 1) × p

If h < 1, return s[1]. If h > N, return s[N]. Otherwise:

    result = s[⌊h⌋] + (h − ⌊h⌋) × (s[⌈h⌉] − s[⌊h⌋])

This is the "exclusive" interpolation method (R-6 in Hyndman & Fan
taxonomy). Do NOT use the "linear" method (R-7) which uses
`h = (N − 1) × p + 1`.

Report percentiles at levels specified in the pipeline config (typically
p5, p25, p50, p75, p95).

## Exponential Moving Average (EMA)

The smoothing factor α is derived from the `halflife` parameter
(in number of observations):

    α = 1 − exp(−ln(2) / halflife)

This is the decay-based formula. Do NOT use the span formula
`α = 2 / (span + 1)` or the center-of-mass formula `α = 1 / (com + 1)`.

Initialization: the first EMA value equals the first valid observation.
Subsequent values:

    ema[i] = α × x[i] + (1 − α) × ema[i − 1]

Null observations are skipped: `ema[i] = ema[i − 1]` when `x[i]` is
null, and the output at that position is also null.

## Rolling Statistics

For a window of size W (must be odd), centered at index i:

    window indices = [max(0, i − W÷2), min(N−1, i + W÷2)]

where ÷ is integer division. At stream boundaries the window is
truncated. If the effective window has fewer valid values than
`rolling_min_window` from the config, the result at that position
is null.

**NaN policy** (per-stream override in pipeline config):
- `"omit"`: skip null values in the window, compute from valid ones
- `"propagate"`: if any value in the window is null, the result is null

Compute `rolling_mean` and `rolling_std` (using **population** standard
deviation within each window, regardless of the global `variance_type`).

## Outlier Detection — Modified Z-Score

Compute the **median** and **MAD** (Median Absolute Deviation) from
all valid observations:

    median = standard statistical median
    MAD = median( |xᵢ − median| )  for all valid xᵢ

The modified Z-score for each observation:

    z_i = |xᵢ − median| / (k × MAD)

where k is `mad_consistency_constant` from the config (1.4826).

**When MAD = 0**: if `|xᵢ − median| < epsilon`, the Z-score is 0.
Otherwise the Z-score is positive infinity (the point is an outlier).

An observation is an **outlier** when `z_i > threshold` (strict greater,
per `outlier_comparison`). If z_i > `extreme_outlier_factor × threshold`,
the finding type is `"extreme_outlier"` (severity from config); otherwise
it is `"outlier"`. Each outlier observation produces exactly one finding
(the more severe type if it qualifies as extreme).

## Gap Analysis

A **gap** exists between consecutive observations when:

    t[i+1] − t[i] > max_gap_seconds

The gap has duration = `t[i+1] − t[i]`. Report only gaps whose
duration ≥ `min_gap_duration` from config. Each qualifying gap produces
a `"data_gap"` finding with evidence containing `start_timestamp`,
`end_timestamp`, and `duration`.

## Stale Data Detection

A **stale run** is a maximal sequence of consecutive observations
(by timestamp order) where all values are identical within epsilon.
If the length of a stale run ≥ `stale_count` (from pipeline config
or `stale_count_default`), generate a `"stale_data"` finding.

Evidence: `start_index`, `end_index`, `run_length`, `value`.

## CUSUM Change-Point Detection

Target (reference level) = mean of the first `cusum_warmup_count`
valid observations. Do NOT use the overall stream mean.

Initialize: `S_high = 0`, `S_low = 0`.

For each observation from index `warmup_count` onward:

    S_high = max(0, S_high + (xᵢ − target) − drift)
    S_low  = min(0, S_low  + (xᵢ − target) + drift)

A **change point** is detected when `S_high > threshold` (upward shift)
or `|S_low| > threshold` (downward shift). After detection, reset
both `S_high` and `S_low` to 0 and continue scanning.

Each detection produces a `"change_point"` finding with evidence
containing `index`, `direction` (`"up"` or `"down"`), `cusum_value`
(the value that exceeded the threshold), and `timestamp`.

## Trend Analysis — Weighted Least Squares

Independent variable: observation index `i = 0, 1, …, N−1`.
Dependent variable: observation value `yᵢ`.

When `trend_weights` is `"uniform"`, all weights `wᵢ = 1.0`.

When `trend_weights` is `"inverse_variance"`, weights are:

    wᵢ = 1.0 / max(rolling_var[i], epsilon)

where `rolling_var[i]` is the rolling population variance at index i.
If `rolling_var[i]` is null, use `wᵢ = 1.0`.

Weighted means:

    x̄_w = Σ(wᵢ × i) / Σ(wᵢ)
    ȳ_w = Σ(wᵢ × yᵢ) / Σ(wᵢ)

Weighted slope and intercept:

    slope = Σ(wᵢ × (i − x̄_w) × (yᵢ − ȳ_w)) / Σ(wᵢ × (i − x̄_w)²)
    intercept = ȳ_w − slope × x̄_w

Residual sum of squares (weighted):

    wss_residual = Σ(wᵢ × (yᵢ − (intercept + slope × i))²)

Report: `slope`, `intercept`, `r_squared` (coefficient of determination).
R² is computed as:

    wss_total = Σ(wᵢ × (yᵢ − ȳ_w)²)
    r_squared = 1 − wss_residual / wss_total

When `wss_total` is 0 (constant values), `r_squared` is null.

## Insufficient Data

If a stream has fewer than `min_observations` valid values, generate
an `"insufficient_data"` finding. Skip all other computations for
that stream except `basic_stats`.

## Findings

Sort per-stream findings by
`(severity_rank, finding_type, index_or_timestamp)`.

Sort global findings by
`(severity_rank, finding_type, stream_id, index_or_timestamp)`.

For findings that reference a specific observation, `index_or_timestamp`
is the observation index. For gap findings, it is `start_timestamp`.
For stale findings, it is `start_index`. Null timestamps sort last.

All floating-point values in the output are rounded to `output_decimals`
decimal places.
