# Replica lag window audit

Inputs live beside this file. Read `policy.json`, `pool_state.json`, `dependencies.json`, `incidents.json`, and every `*.json` file directly under `shards/`. Paths under `ledger/` and `anchors/` are packaging noise only.

## Canonical JSON

Emit every artifact as JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Policy

- `grace_days_after_failover` (positive integer): inclusive day window after a `failover` incident during which lag verdicts are suppressed (see Grace).
- `median_reject_ratio` (number): outlier cutoff multiplier for the lag median window.
- `median_window_k` (positive integer): count of most recent samples per shard used for lag aggregation.
- `tier_thresholds` maps tier name (`gold`, `silver`, `bronze`) to objects with `warn_lag_bytes` and `critical_lag_bytes` (non-negative integers, warn strictly less than critical).
- `witness_skew_bytes` (non-negative integer): maximum allowed gap between witness and data lag on the latest sample.

## Pool state

- `current_day` (integer): evaluation day for grace windows and incident acceptance.

## Dependencies

`edges` is an array of objects `{parent, child}` naming shard ids. Unknown ids are ignored. Build a directed graph from parent to child.

## Incidents

`events` is processed after sorting by ascending `day`, then ascending `shard_id`. Only events with `day <= current_day` apply. Kinds:

- `embargo_downstream`: the named shard and every transitive child shard are embargoed.
- `failover`: records a failover day for the shard (later events on the same shard replace the stored day).
- `force_lag_verdict`: sets `forced_verdict` to `lag_warn` or `lag_critical` for the shard.
- `freeze_shard`: the shard is frozen.

## Shard samples

Each shard file provides `shard_id`, `tier` (`gold`, `silver`, or `bronze`), and `samples` (array of `{day, lag_bytes, witness_lag_bytes}`). Sort samples by `day` ascending before use.

### Lag window and effective lag

Let `K = median_window_k`. Take the last `K` samples (or all samples when fewer than `K`). Compute `median_lag_bytes` as the median of their `lag_bytes` values (even count: average of the two central values with integer division toward zero). When `median_lag_bytes` is zero, keep every window sample. Otherwise drop any sample where `abs(lag_bytes - median_lag_bytes) > median_reject_ratio * median_lag_bytes` (strict inequality). `effective_lag_bytes` is the median of the remaining `lag_bytes` values using the same median rule; when no samples remain, use `0`.

### Witness skew

Let the latest sample be the one with the greatest `day` (tie-break: last in day-sorted order). `witness_desync` is true when `witness_lag_bytes - lag_bytes > witness_skew_bytes` on that sample.

### Lag verdict

Map `effective_lag_bytes` against the shard tier thresholds: `lag_ok` when below warn, `lag_warn` when at or above warn but below critical, `lag_critical` when at or above critical. When grace applies (see below), replace `lag_warn` and `lag_critical` with `lag_ok` before other overrides. Apply `force_lag_verdict` after grace. Frozen shards use final verdict `frozen`. Embargoed shards use `embargoed`. When `witness_desync` is true, final verdict is `hold` regardless of lag or forced lag verdicts (freeze still wins).

Grace applies when the shard has a stored failover day `F` and `current_day <= F + grace_days_after_failover - 1`.

## Flush readiness

Unless blocked, a shard is `flush_ready` when its final verdict is `lag_ok`. Blocking reasons (first match wins in this list when multiple apply): `blocked_frozen`, `blocked_embargo`, `blocked_witness`, `blocked_cycle`, `blocked_parent`, else `flush_ready` or `not_due`. `not_due` when the final verdict is `lag_warn` or `lag_critical` and no higher-priority block applies. A shard in a dependency cycle is `blocked_cycle`. A shard is `blocked_parent` when any parent exists and the parent's final verdict is not `lag_ok`, or the parent's `flush_status` is not `flush_ready`. A shard with `witness_desync` is `blocked_witness`. Embargoed shards are `blocked_embargo`. Frozen shards are `blocked_frozen`.

## Outputs

Write five files to the audit directory:

1. `shard_profiles.json` with `current_day` copied from pool state and `profiles` sorted by `shard_id` ascending. Each profile object includes `effective_lag_bytes`, `embargoed` (bool), `final_verdict`, `flush_status`, `grace_active` (bool), `shard_id`, `tier`, and `witness_desync` (bool).
2. `dependency_plan.json` with keys `cycles` then `order`. `cycles` is an array of arrays; each inner array lists shard ids in one directed cycle, sorted ascending, and the outer array is sorted by its first element ascending. `order` is a topological list of shard ids not appearing in any cycle: parents before children, ties broken by ascending `shard_id` within each ready wave.
3. `flush_plan.json` with `entries` sorted by `shard_id` ascending. Each entry has `flush_status`, `reasons` (sorted unique strings explaining blocks), and `shard_id`. Use exactly these reason tokens when applicable: `frozen`, `embargo`, `witness_desync`, `cycle`, `parent:<parent_shard_id>` (one per blocking parent), and `lag` when `flush_status` is `not_due`.
4. `incident_trace.json` with `applied` sorted by `day` then `shard_id`. Each row copies `day`, `kind`, `shard_id`, and adds `effect` (short string: `embargo`, `failover`, `force`, `freeze`).
5. `summary.json` with `current_day`, `flush_ready_total`, `hold_total`, `shards_total`, and `tiers` mapping tier name to counts of `lag_ok`, `lag_warn`, and `lag_critical` among profiles whose final verdict is one of those three (frozen, embargoed, and hold are excluded from tier counts).

## Tooling

Read `RLA_DATA_DIR` defaulting to `/app/replag` and `RLA_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
