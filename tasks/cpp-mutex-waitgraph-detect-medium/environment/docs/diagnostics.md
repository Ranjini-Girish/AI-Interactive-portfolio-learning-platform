# Diagnostic codes

Closed set used in `diagnostics.json`. Severity rank for sorting: error (0), warning (1), note (2).

| Code | Severity |
|------|----------|
| `E_UNKNOWN_MUTEX` | error |
| `E_BLOCKED` | error |
| `E_BUSY_TRY` | error |
| `E_IDLE` | error |
| `E_WRONG_OWNER` | error |
| `W_CYCLE` | warning |
| `N_TICK` | note |
| `N_ACQUIRE` | note |
| `N_WAKE` | note |

Each diagnostic object has string `code`, nullable string `mutex`, and string `severity`.
