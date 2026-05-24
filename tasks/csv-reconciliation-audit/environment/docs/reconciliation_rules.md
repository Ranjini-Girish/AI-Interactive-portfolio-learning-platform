# Reconciliation Rules

## Settlement Matching
Each transaction should have exactly one settlement record matched by `txn_id`.

## Amount Tolerance
The absolute difference between transaction amount and settled amount must not
exceed the configured `amount_tolerance`. Differences within tolerance are accepted.

## Ledger Balance
For each transaction, the sum of all debit entries must equal the sum of all
credit entries in the ledger. Any nonzero difference constitutes an imbalance.

## Duplicate Detection
Two transactions are duplicates if they share the same `account_id`, `amount`,
and `description`, and their timestamps fall within `duplicate_window_days` of
each other.

## Currency Conversion
EUR amounts are converted to USD using the `EUR_USD` rate from the rates
configuration before any cross-currency aggregation.
