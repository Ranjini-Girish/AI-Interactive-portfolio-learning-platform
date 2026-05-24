# Error Types

| Type | Description |
|------|-------------|
| `amount_mismatch` | Settlement amount differs from transaction amount beyond tolerance |
| `ledger_imbalance` | Debit and credit totals for a transaction do not balance |
| `unsettled` | Transaction has no corresponding settlement record |
| `orphan` | Settlement references a transaction that does not exist |
| `duplicate` | Two transactions match on account, amount, and description within window |
