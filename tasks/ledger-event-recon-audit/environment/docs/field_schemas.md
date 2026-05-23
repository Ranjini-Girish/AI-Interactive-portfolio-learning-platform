# Input field schemas

This file enumerates every field of every input record. The JSON Schema
counterparts live under `/app/docs/schemas/` for programmatic consumption.

## `accounts.json`

```
{ "accounts": [ <Account>, ... ] }
```

Each `Account`:

| Field                          | Type           | Notes |
| ------------------------------ | -------------- | ----- |
| `id`                           | string         | unique account id (ASCII) |
| `currency`                     | string         | ISO-style code; every account in a dataset uses the same currency, so no FX conversion is needed |
| `opening_balance_cents`        | signed int     | starting balance |
| `tier`                         | "basic" \| "premium" | informational |
| `account_type`                 | "checking" \| "savings" \| "credit" | overdraft floor depends on this |
| `status`                       | "active" \| "frozen" \| "closed" | gates events; see `policy.json` |
| `daily_withdraw_limit_cents`   | signed int OR `null` | per-account override; when `null`, use `policy.default_daily_withdraw_limit_cents` |

## `events.json`

```
{ "events": [ <Event>, ... ] }
```

Each `Event` (the `seq` field is strictly ascending and dense from 0;
the `day` field is monotonically non-decreasing in `seq`):

| Field            | Type           | Notes |
| ---------------- | -------------- | ----- |
| `seq`            | non-neg int    | unique per event |
| `day`            | non-neg int    | logical day index |
| `op`             | one of `deposit`, `withdraw`, `transfer`, `hold`, `release`, `reverse` | |
| `account`        | string         | the issuing/source account |
| `target_account` | string OR `null` | the destination account for `transfer`; `null` for every other op |
| `amount_cents`   | positive int OR `null` | `null` (and ignored) for `release` and `reverse`; positive otherwise |
| `currency`       | string OR `null` | matches the involved account(s); ignored for `release` and `reverse` |
| `reverses_seq`   | non-neg int OR `null` | for `reverse`, the `seq` of the original event being undone; for `release`, the `seq` of the original `hold` being released; `null` for every other op |

## `snapshots.json`

```
{ "expected_balances": { "<account_id>": <int_cents>, ... } }
```

A flat mapping from account id (string) to expected closing balance (signed
integer cents). Accounts present in `accounts.json` but missing from this
map are reconciled as `"unsnapshotted"` and emit no diagnostic.

## `policy.json`

| Key | Type | Meaning |
| --- | ---- | ------- |
| `severity_ranks` | object: `{<severity>: int}` | `lower` rank == more severe; the closed set of severity names is `error`, `warning`, `note`. Used both to populate every diagnostic's `severity_rank` and to drive `event_diagnostics.json` sort order |
| `default_daily_withdraw_limit_cents` | non-neg int | account-level override wins when non-null |
| `overdraft_allowed_account_types` | list[string] | the subset of `account_type` values whose `withdraw`/`transfer` may go negative; in this benchmark only the literal `credit` value uses a negative floor (`-credit_account_credit_limit_cents`); any other listed type still uses zero |
| `credit_account_credit_limit_cents` | non-neg int | credit-account overdraft floor magnitude |
| `reversal_window_days` | non-neg int | a `reverse` at day `D` may target an event whose `day` is at least `D - reversal_window_days` |
| `hold_max_age_days` | non-neg int | max-allowed age for a still-active hold at trace end |
| `transfer_self_action` | "error" \| "ignore" | how to handle `transfer` with `target_account == account` |
| `frozen_account_action` | "block_all" \| "allow_credits_only" | how to handle events touching frozen accounts |
| `closed_account_action` | "block_all" \| "allow_credits_only" | how to handle events touching closed accounts |
