# Rank Correlation Specification

For each pair of groups with equal sample sizes within an experiment, compute the Spearman rank correlation coefficient.

## Ranking with Ties

For each group's values, assign ranks using the average-rank method:

1. Sort the values.
2. Assign ranks 1, 2, ..., n based on sorted position.
3. For tied values (identical values), replace their individual ranks with the average of the ranks they span.

Example: values [3, 1, 4, 1] get ranks: value 1 appears at positions 1 and 2, so both get rank 1.5; value 3 is at position 3, rank 3; value 4 is at position 4, rank 4. Result: [3.0, 1.5, 4.0, 1.5].

## Spearman Correlation

When ties are present, use the Pearson correlation formula applied to the ranks:

`r_s = sum((R_i - R_mean) * (S_i - S_mean)) / sqrt(sum((R_i - R_mean)^2) * sum((S_i - S_mean)^2))`

where R_i and S_i are the average ranks of the two groups, and R_mean and S_mean are their respective mean ranks.

Do NOT use the simplified formula `r_s = 1 - 6*sum(d_i^2) / (n^3 - n)` when ties are present, as it gives incorrect results.

## Correlation Matrix

For each experiment, produce a correlation matrix. The matrix rows and columns correspond to the groups sorted alphabetically by group name. Entry (i, j) is the Spearman correlation between group i and group j. Diagonal entries are 1.0.

If two groups have different sample sizes, their correlation entry is null (correlation requires paired observations of equal length).

## Edge Cases

If n < 3, the correlation is null.

If all values in a group are identical (zero variance in ranks), the correlation with any other group is null (undefined due to division by zero).
