# Reconciliation overview

This is a quick narrative for engineers who haven't worked with the live
ledger before. The authoritative spec for the audit run lives in
`instruction.md` at the task root; nothing in this file overrides it.

## What the auditor produces

A single JSON document at the path passed via `--out`. The top-level shape is
fixed; every list inside has an explicit, deterministic sort order documented
in `instruction.md`.

## Categories of findings

- **account_findings** — per-account balance and velocity issues:
  `negative_open_balance`, `available_below_floor`, `velocity_breach`.
- **stuck_holds** — holds whose expiry has passed without a release.
- **fee_anomalies** — mismatches between expected and recorded transaction
  fees: `fee_amount_mismatch`, `fee_missing`.
- **chain_anomalies** — structural defects in transaction chains:
  `cycle_in_chain`, `double_resolution`, `duplicate_refund`,
  `post_close_chain_activity`.
- **fx_findings** — currency conversion issues: `fx_missing`, `fx_drift`.
- **data_quality** — orphan counts and the materialized-view staleness check.

## Tenant clock skew

`tenants.audit_day_offset_min` is applied **only** during the FX rate lookup
(`expected_day = floor((ts_utc - audit_day_offset_min * 60) / 86400)`).
It is **not** applied to event ordering, chain traversal, velocity counting,
or the `view_staleness_seconds` calculation (which uses raw UTC: `current_day_end - MAX(committed_ts)`).

## Day arithmetic

Every `*_day` column is an opaque integer identifier — never interpret it as a
calendar date. To go between `ts_utc` and a day identifier:

```
day = ts_utc // 86400
```

Day boundaries are `[D * 86400, (D+1) * 86400)` in UTC seconds.
