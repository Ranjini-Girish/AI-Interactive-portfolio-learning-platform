# Output format

All four output files are UTF-8, ASCII-only, two-space-indented JSON with
keys lexicographically sorted at every depth and a single trailing newline.

## `account_state.json`

```
{ "accounts": [ <AccountState>, ... ] }
```

Sorted by `id` ASCII-ascending. Each `AccountState`:

| Key | Type | Notes |
| --- | ---- | ----- |
| `active_holds` | array | sorted by `seq` ascending; each entry `{amount_cents, day, seq}` is a hold that was issued during the trace and never released |
| `balance_cents` | signed int | the final on-ledger balance (does not subtract holds) |
| `hold_amount_total_cents` | non-neg int | sum of `amount_cents` over `active_holds` |
| `id` | string | account id |
| `n_reversed_events` | non-neg int | count of events on this account (as either `account` or `target_account`) that were the *target* of a successful `reverse` |
| `status` | string | the account's `status` from `accounts.json` (the simulator does not mutate status during the trace) |
| `total_deposits_cents` | non-neg int | sum of every successful credit leg (the credit leg of a successful `deposit`, the credit leg of a successful `transfer`, the inverse credit leg of a successful `reverse` of a `withdraw`, and the source-credit-back leg of a successful `reverse` of a `transfer`) |
| `total_withdrawals_cents` | non-neg int | sum of every successful debit leg (the debit leg of a successful `withdraw`, the debit leg of a successful `transfer`, and the inverse debit legs of a successful `reverse` of a `deposit` or the target-debit-back leg of a successful `reverse` of a `transfer`) |

A `hold` is **not** a deposit or withdrawal; it does not contribute to either
total. A `release` likewise contributes to neither total. Reversals therefore
only feed into the totals via their inverse legs.

## `event_diagnostics.json`

```
{ "diagnostics": [ <Diagnostic>, ... ] }
```

Sort order is documented in `diagnostic_codes.md`. Each `Diagnostic` has the
keys `account`, `code`, `evidence`, `seq`, `severity`, `severity_rank` —
nothing else.

## `reconciliation_report.json`

```
{ "accounts": [ <ReconciliationRow>, ... ] }
```

Sorted by `account` ASCII-ascending. Each `ReconciliationRow`:

| Key | Type | Notes |
| --- | ---- | ----- |
| `account` | string | the account id |
| `actual_balance_cents` | signed int | the final `balance_cents` from `account_state.json` |
| `delta_cents` | signed int OR `null` | `actual - expected` when the snapshot has the account, else `null` |
| `expected_balance_cents` | signed int OR `null` | the value from `snapshots.expected_balances`, or `null` when the snapshot is missing the account |
| `status` | "matched" \| "mismatched" \| "unsnapshotted" | `matched` iff `delta_cents == 0`, `unsnapshotted` iff `expected_balance_cents` is `null`, else `mismatched` |

## `compliance_summary.json`

```
{
  "by_severity": { <severity>: <count>, ... },
  "totals": {
    "accounts_total": <int>,
    "events_total": <int>,
    "mismatched_accounts": <int>,
    "n_active_holds_total": <int>,
    "total_diagnostics": <int>,
    "total_reversed_events": <int>
  }
}
```

`by_severity` always contains every key listed in `policy.severity_ranks`
(zeros for absent ones). `totals.events_total` is the count of every event
in `events.json` regardless of whether it was rejected. Per-account values
in `totals` are the sum across every account in `accounts.json`.
