# Convergence Analysis

## Empirical Convergence Order

Given two runs at sample sizes N_small < N_large with absolute errors
E_small and E_large respectively, the empirical convergence order is:

    order = log(E_small / E_large) / log(N_large / N_small)

This measures how fast the error decreases as sample size grows.  For
standard Monte Carlo the theoretical order is 0.5 (error ~ 1/sqrt(N)).

## Null Conditions

Report the empirical order as null when any of:
- E_small <= E_large (error did not decrease)
- E_small == 0 (perfect estimate at smaller size)
- E_large == 0 (perfect estimate at larger size)

## Consecutive Pairs

Convergence entries are computed for each consecutive pair of sample sizes
in the configured list.  For sizes [100, 500, 1000, 5000] there are three
pairs per (function, method) combination: (100,500), (500,1000), and
(1000,5000).
