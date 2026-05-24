# Variance Estimation

## Population Variance

Throughout this system, "sample variance" refers to the **population
variance** of the computed values — that is, using denominator N:

    Var = (1/N) * sum_{i=1}^{N} (v_i - v_bar)^2

where v_i are the per-sample values produced by the method (not the raw
function evaluations) and v_bar is their arithmetic mean.

For Crude MC, v_i = f(x_i).
For Antithetic, v_i = (f(x_i) + f(1-x_i)) / 2.
For Stratified, the overall variance uses within-stratum population
variances combined as: Var = (1/K^2) * sum_k (sigma_k^2 / n_k).
For Control Variates, v_i = f(x_i) - c*(g(x_i) - E[g]).

## Standard Error

    SE = sqrt(Var / N)

where Var is the population variance defined above and N is the number of
samples (not the number of function evaluations).

## Cost-Adjusted Variance

To compare methods fairly, multiply the variance by the number of function
evaluations per sample:

    CAV = Var * evaluations_per_sample

This accounts for the computational cost difference: antithetic and control
variates require 2 evaluations per sample, while crude and stratified
require 1.

## Efficiency Ratio

The efficiency ratio of a method relative to crude MC is:

    ER = CAV_crude / CAV_method

A ratio > 1 means the method is more efficient.  Report null when either
CAV is null or the method's CAV is zero.
