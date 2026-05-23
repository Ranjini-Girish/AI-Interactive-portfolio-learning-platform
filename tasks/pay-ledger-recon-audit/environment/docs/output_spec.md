# Output Specification

## Report Structure

```json
{
  "schema_version": 1,
  "as_of_day": <int>,
  "summary": { ... },
  "account_findings": [ ... ],
  "stuck_holds": [ ... ],
  "fee_anomalies": [ ... ],
  "chain_anomalies": [ ... ],
  "fx_findings": [ ... ],
  "data_quality": { ... }
}
```

- `as_of_day`: `policy.current_day`
- All `*_day` fields are opaque integer day identifiers
- Severity ranks: critical=0, high=1, medium=2, low=3

## Account Findings

Non-closed accounts only (closed_day is NULL or > current_day).

- `negative_open_balance` (critical): open_balance < 0
- `available_below_floor` (high/medium): available < tenant minimum; high if gap >= severe_floor_breach_minor
- `velocity_breach` (medium): captures today >= velocity_threshold_per_day

Sort: severity rank, finding_code, tenant_id, account_id (all ASCII)

## Balance Calculation

Non-voided transactions only. A transaction is voided when status == "voided"; rows with NULL status are treated as non-voided and included in balance computation.

| kind | contribution |
|------|-------------|
| capture | -amount_minor |
| refund | +amount_minor |
| chargeback | +amount_minor |
| fee | -amount_minor |
| auth, hold, release | 0 |

Uncleared holds: released_ts IS NULL AND expires_ts >= current_day_end_utc_seconds
Available = open_balance - uncleared_holds

## Stuck Holds

A hold is stuck when ALL of:
- released_ts IS NULL
- expires_ts < current_day_end_utc_seconds (boundary exclusive)
- account is non-closed (or account doesn't exist)

Sort: expires_ts ascending, hold_id ascending

## Fee Calculation

For captures: expected_fee = bankers_round(amount_minor * fee_bps / 10000)

Rule matching: mcc must match AND pattern.lower() in merchant_name.lower()
Priority: smallest priority integer wins; ties broken by rule_id ASCII

Fallbacks: default_fee_bps (verified) or unverified_fee_bps (unverified)

- `fee_missing`: no fee transaction for non-voided capture
- `fee_amount_mismatch`: actual != expected

Sort: finding_code, tx_id

## Chain Anomalies

- `cycle_in_chain` (critical): ancestors form a cycle
- `double_resolution` (critical): chain has both refund AND chargeback
- `duplicate_refund` (high): same (account_id, parent_tx_id, amount_minor)
- `post_close_chain_activity` (medium): resolution_day > closed_day

Sort: severity rank, finding_code, chain_root

## FX Findings

For non-voided transactions where currency != tenant base_currency:

expected_day = floor((ts_utc - audit_day_offset_min * 60) / 86400)

- `fx_missing` (high): no fx_rate row for expected_day
- `fx_drift` (medium): fx_micro != rate_micro

Sort: severity rank, finding_code, tx_id

## Data Quality

- `orphan_tenant_accounts`: accounts with unknown tenant_id
- `orphan_holds`: holds with unknown account_id
- `unknown_kind_rows`: transactions with null/unrecognized kind
- `view_staleness_seconds`: current_day_end - MAX(committed_ts) from mv_daily_balances
- `view_stale`: staleness > balance_view_max_staleness_min * 60
- `fx_unconvertible_count`: number of fx_missing findings
- `negative_amounts`: transactions with amount_minor < 0

## Summary

- `as_of_day`: same as top-level `as_of_day` (i.e. `policy.current_day`)
- `tenant_count`, `non_closed_account_count`
- `by_severity`: always all four keys (critical, high, medium, low)
- `by_finding_code`: sorted ASCII
- `audit_run_seconds`: wall-clock duration

Aggregates findings from account_findings, fee_anomalies, chain_anomalies, fx_findings. Stuck holds are NOT findings.
