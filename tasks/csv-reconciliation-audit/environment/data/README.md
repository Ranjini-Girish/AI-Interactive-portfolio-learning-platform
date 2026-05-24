# Data Dictionary

## transactions.csv
Primary record of all financial transactions.
- `txn_id`: Unique transaction identifier
- `account_id`: Account that initiated the transaction
- `amount`: Transaction amount in the specified currency
- `currency`: ISO currency code (USD or EUR)
- `timestamp`: ISO 8601 timestamp (UTC)
- `description`: Free-text description (may contain commas)

## settlements.csv
Records of settled (processed) transactions.
- `settlement_id`: Unique settlement identifier
- `txn_id`: Reference to the original transaction
- `settled_amount`: Amount actually settled
- `settlement_date`: Date of settlement (MM/DD/YYYY format)
- `status`: Settlement status
- `fee`: Processing fee charged

## ledger.csv
Double-entry bookkeeping records.
- `entry_id`: Unique ledger entry identifier
- `txn_id`: Reference to the original transaction
- `debit`: Debit amount (0.00 if credit entry)
- `credit`: Credit amount (0.00 if debit entry)
- `account_code`: General ledger account code
- `posted_date`: Date posted (YYYY-MM-DD format)
