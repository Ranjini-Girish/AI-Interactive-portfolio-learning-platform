# Monte Carlo Integration Methods

## Crude Monte Carlo

The simplest MC estimator approximates an integral over [a,b] by sampling
uniformly and averaging function values:

    I_hat = (1/N) * sum_{i=1}^{N} f(x_i),  x_i ~ Uniform(a,b)

For [0,1] this simplifies to the sample mean of f(x_i).

## Antithetic Variates

Reduces variance by pairing each sample with its complement.  For each
uniform sample x_i in [0,1], evaluate both f(x_i) and f(1 - x_i), then
average the pair:

    y_i = ( f(x_i) + f(1 - x_i) ) / 2
    I_hat = (1/N) * sum_{i=1}^{N} y_i

The estimator uses N original samples but 2N function evaluations.

## Stratified Sampling

Partitions [0,1] into K equal strata [k/K, (k+1)/K] for k = 0, ..., K-1.
Within each stratum, samples are transformed from uniform [0,1] draws u_j
into stratum points:

    x_{k,j} = (k + u_j) / K

The per-stratum mean is computed, then the overall estimate is the average
of stratum means:

    I_hat = (1/K) * sum_{k=0}^{K-1} mean(f(x_{k,j}))

Sample allocation: if N is not divisible by K, the first (N mod K) strata
receive ceil(N/K) samples and the remaining strata receive floor(N/K).

## Control Variates

Uses a correlated "control" function g(x) with known expectation E[g(X)].
The optimal coefficient c* minimises the variance of the adjusted estimator:

    c* = Cov(f, g) / Var(g)

Adjusted values:

    y_i = f(x_i) - c* * (g(x_i) - E[g(X)])

The estimator is I_hat = (1/N) * sum y_i.

Note: c* is computed from population covariance and population variance
(both with denominator N), while E[g(X)] is the analytical expected value
provided in the configuration, not the sample mean of g.
