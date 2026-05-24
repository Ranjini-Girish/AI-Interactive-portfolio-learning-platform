# Bootstrap Confidence Interval Specification

For each pairwise comparison, compute a bootstrap confidence interval for the difference in means using the percentile method.

## Pseudorandom Number Generator

The bootstrap uses a deterministic PRNG to ensure reproducible results. The PRNG is a Park-Miller linear congruential generator (Lehmer RNG):

`next_state = (16807 * state) % 2147483647`

The random float in [0, 1) is: `state / 2147483647`

The initial seed is specified in the pipeline configuration (`bootstrap_seed`). The PRNG state is initialized once at the start of the entire pipeline and carried forward sequentially across all experiments and comparisons. Experiments are processed in sorted order by experiment_id; within each experiment, comparisons are processed in sorted order by (group_a, group_b).

## Resampling Procedure

For each bootstrap iteration b = 1, ..., B (where B is `bootstrap_iterations` from config):

1. Resample group_a with replacement: for each of n1 positions, generate a random index `floor(random_float * n1)` and pick the value at that index from the original group_a.
2. Resample group_b with replacement: for each of n2 positions, generate a random index `floor(random_float * n2)` and pick the value at that index from the original group_b.
3. Compute the mean difference: `mean(resampled_a) - mean(resampled_b)`.

## Percentile Method

After collecting B bootstrap mean differences:

1. Sort the B differences in ascending order.
2. Compute the lower bound at percentile `alpha/2` and upper bound at percentile `1 - alpha/2`, where `alpha = 1 - confidence_level`.
3. The percentile at fraction p of N sorted values uses linear interpolation: `index = p * (N - 1)`. The value is `sorted[floor(index)] + frac(index) * (sorted[ceil(index)] - sorted[floor(index)])`.

## Edge Cases

If either group has n < 2, the bootstrap CI is null for both bounds.
