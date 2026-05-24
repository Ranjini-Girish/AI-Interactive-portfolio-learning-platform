# Retry schedule replay

Each endpoint references a retry policy id in `retry_policies.json`.

For a failed attempt (status `failed` or `timeout`, not `success` or `dead_letter`) that is followed by another attempt in the same delivery:

Expected gap until the next attempt starts: `min(max_delay_ms, base_delay_ms * multiplier^(next_attempt_number - 2) * (1 + jitter_pct/100))` where `jitter_pct` is on the **failed** attempt record (default 0 if missing).

Compare to actual gap: `next.sent_at - failed.sent_at`. Violation if actual < expected - 1 ms (tolerance 1 ms).

Terminal attempt: status `dead_letter`, or `attempt_number >= max_attempts` with a non-success status.

Any `success` attempt after a terminal attempt in the same delivery is a policy violation.

Attempts must be numbered contiguously starting at 1; missing numbers produce `orphan_attempt_gap`.
