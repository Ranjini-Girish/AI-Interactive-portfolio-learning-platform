package mc;

/**
 * Assembles the final audit report JSON containing:
 *   - metadata (function/method counts, sample sizes, seed)
 *   - results (per function/method/sample_size evaluation records)
 *   - convergence (empirical convergence order between consecutive sample sizes)
 *   - efficiency_summary (cost-adjusted variance ratios at the largest sample size)
 *
 * Output is written as JSON with 2-space indent and a trailing newline.
 */
public class AuditReport {
    // TODO: implement report assembly and JSON serialization
}
