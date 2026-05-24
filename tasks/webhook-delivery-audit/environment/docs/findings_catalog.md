# Findings and risk

Emit one finding per violation instance with fields: `endpoint_id`, `delivery_id`, `finding`, `severity` (from policy mapping), `detail`, `risk_score`.

Risk score: `round(severity_multiplier[severity] * depth_weight_base^attempt_number, output_decimals)` where depth is the attempt_number on which the violation was detected.

Global `findings` sorted by: severity rank ascending, endpoint_id, delivery_id, finding name, attempt_number (if present in evidence else 0).

`aggregate_risk_score` in summary: geometric mean of all finding risk_scores with value > 0; 0 if none. Round to output_decimals.

`avg_attempts_to_success`: harmonic mean of attempt counts for deliveries whose final attempt status is `success`; omit deliveries that never succeed from the mean; 0 if none succeeded.

`failure_rate`: failed_or_terminal_deliveries / total_deliveries per endpoint (delivery fails if final status is not `success`).

Clock skew finding when `abs(received_at - sent_at) > clock_skew_ms` on any attempt.

Duplicate `delivery_id` values within the same endpoint log file (across the deliveries array) each produce a finding.
