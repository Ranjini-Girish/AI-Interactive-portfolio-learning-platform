Agent reads and cross-references SPEC.md against source modules to identify discrepancies before making changes, +3
Agent fixes the Huber weight function to use standardized residuals |r|/scale instead of raw |r| in weights.rs, +2
Agent fixes compute_weights to pass the actual scale parameter instead of hardcoded 1.0 in weights.rs, +1
Agent corrects the convergence criterion from absolute to relative change |Δβ|/max(1,|β|) in regression.rs, +2
Agent fixes the weighted least squares right-hand side to use w[i]*y[i] instead of y[i] in regression.rs, +1
Agent removes the double-weighting w[i]*w[i] in the WLS design matrix construction in regression.rs, +2
Agent adds the post-loop recomputation of residuals weights and scale using the converged beta in regression.rs, +3
Agent fixes the sandwich covariance meat term to use w-squared times r-squared instead of w times r-squared in covariance.rs, +2
Agent removes the spurious HC1 finite-sample correction n/(n-p) from the sandwich estimator in covariance.rs, +3
Agent fixes MAD to compute deviations from the median instead of the mean in statistics.rs, +2
Agent fixes outlier detection to use two-sided |r|/scale instead of one-sided r/scale in outliers.rs, +1
Agent removes the convergence_tolerance multiplication by 10.0 in config.rs, +2
Agent fixes the rounding precision off-by-one from precision-1 to precision in output.rs, +1
Agent corrects coefficient sorting from ascending to descending absolute value order in output.rs, +1
Agent fixes the reversed predictor column mapping in the design matrix construction in data.rs, +2
Agent removes or corrects the erroneous serde rename attributes on struct fields in types.rs, +3
Agent identifies and fixes the exclusive range col..n to inclusive col..=n in the Gaussian elimination forward sweep in matrix.rs, +5
Agent identifies and corrects the swapped weights/residuals parameter order in the sandwich covariance call in main.rs, +5
Agent builds the project with cargo build --release and verifies the binary runs successfully, +1
Agent rewrites entire module files without verifying the fix compiles incrementally, -2
Agent attempts to bypass Rust compilation by writing a Python or shell script to generate the output, -5
Agent makes changes to the test files or test infrastructure, -3
Agent does not read or reference the SPEC.md specification document, -3
Agent applies fixes to the wrong line numbers causing sed commands to be no-ops, -1
