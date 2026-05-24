# Conjugate Gradient Solver Notes

## Preconditioned CG Algorithm

The Jacobi-preconditioned CG method modifies the standard CG algorithm
by using the diagonal of K as a preconditioner:

    M = diag(K)
    z = M^{-1} * r

The preconditioned CG iteration:

1. r_0 = b - A*x_0
2. z_0 = M^{-1} * r_0
3. p_0 = z_0
4. For k = 0, 1, 2, ...
   a. alpha_k = (r_k . z_k) / (p_k . A*p_k)
   b. x_{k+1} = x_k + alpha_k * p_k
   c. r_{k+1} = r_k - alpha_k * A*p_k
   d. Check convergence: ||r_{k+1}|| < tol
   e. z_{k+1} = M^{-1} * r_{k+1}
   f. beta_k = (r_{k+1} . z_{k+1}) / (r_k . z_k)
   g. p_{k+1} = z_{k+1} + beta_k * p_k

## Convergence

The solver should converge for well-conditioned symmetric positive-definite
systems. If the system does not converge within the maximum number of
iterations, the solver should still return the best solution found.
