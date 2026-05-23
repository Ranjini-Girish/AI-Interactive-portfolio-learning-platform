# Schema reference

The live ledger uses the following SQLite schema. See
`/app/data/migrations/001_schema.sql` for the canonical DDL.

## tenants

| column                | type    | notes |
|-----------------------|---------|-------|
| `tenant_id`           | TEXT PK | |
| `jurisdiction`        | TEXT    | regulatory region |
| `base_currency`       | TEXT    | ISO-4217 |
| `audit_day_offset_min`| INTEGER | clock-skew offset for day-bucketing |
| `minimum_balance_minor` | INTEGER | floor for available-balance check |

## accounts

| column        | type    | notes |
|---------------|---------|-------|
| `account_id`  | TEXT PK | |
| `tenant_id`   | TEXT    | not enforced via FK |
| `currency`    | TEXT    | account-side currency |
| `opened_day`  | INTEGER | opaque day identifier |
| `closed_day`  | INTEGER (nullable) | day the account was closed |
| `status`      | TEXT    | free-form |

## merchants

| column        | type    | notes |
|---------------|---------|-------|
| `merchant_id` | TEXT PK | |
| `name`        | TEXT    | |
| `mcc`         | TEXT    | merchant category code |
| `kyc_status`  | TEXT    | `verified` or `unverified` |

## merchant_category_rules

| column     | type    | notes |
|------------|---------|-------|
| `rule_id`  | TEXT PK | |
| `priority` | INTEGER | smallest wins |
| `pattern`  | TEXT    | substring match against `merchants.name`, case-insensitive |
| `mcc`      | TEXT    | must equal `merchants.mcc` |
| `fee_bps`  | INTEGER | basis points (1/10000) |

## transactions

| column         | type    | notes |
|----------------|---------|-------|
| `tx_id`        | TEXT PK | |
| `account_id`   | TEXT    | |
| `kind`         | TEXT (nullable) | one of `auth`, `capture`, `refund`, `chargeback`, `fee`, `hold`, `release` |
| `amount_minor` | INTEGER | minor currency units; never floats |
| `currency`     | TEXT    | ISO-4217 |
| `ts_utc`       | INTEGER | UTC seconds |
| `sequence_id`  | INTEGER | tie-breaker when `ts_utc` collides |
| `parent_tx_id` | TEXT (nullable) | chains transactions together |
| `status`       | TEXT (nullable) | `voided` excludes from balance/finding pipelines |
| `merchant_id`  | TEXT (nullable) | nullable for funding/internal moves |
| `fx_micro`     | INTEGER (nullable) | recorded conversion micro-rate |

## holds

| column         | type    | notes |
|----------------|---------|-------|
| `hold_id`      | TEXT PK | |
| `account_id`   | TEXT    | |
| `amount_minor` | INTEGER | |
| `placed_ts`    | INTEGER | UTC seconds |
| `expires_ts`   | INTEGER | UTC seconds |
| `released_ts`  | INTEGER (nullable) | explicit release timestamp |
| `reason`       | TEXT (nullable) | |

## fx_rates

| column       | type    | notes |
|--------------|---------|-------|
| `day`        | INTEGER | opaque day identifier |
| `base`       | TEXT    | ISO-4217 |
| `quote`      | TEXT    | ISO-4217 |
| `rate_micro` | INTEGER | micro-units (rate * 1_000_000) |
| PRIMARY KEY  | (`day`, `base`, `quote`) | |

## mv_daily_balances

| column         | type    | notes |
|----------------|---------|-------|
| `account_id`   | TEXT    | |
| `day`          | INTEGER | opaque day identifier |
| `balance_minor`| INTEGER | snapshot value |
| `committed_ts` | INTEGER | UTC seconds; drives staleness check |
| PRIMARY KEY    | (`account_id`, `day`) | |
