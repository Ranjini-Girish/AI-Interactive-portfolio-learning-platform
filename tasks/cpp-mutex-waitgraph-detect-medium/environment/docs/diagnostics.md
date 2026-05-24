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

## Per-code `mutex` semantics

Exactly one code is genuinely resource-less; every other code carries the name of the mutex its triggering event named.

| Code | `mutex` value |
|------|---------------|
| `N_TICK` | `null` (the `tick` event has no mutex; the `mutex` field on a tick event is itself `null`). |
| `N_ACQUIRE` | the name of the mutex that just transitioned from unowned to owned. |
| `N_WAKE` | the name of the mutex whose released ownership was handed to a dequeued waiter. |
| `E_UNKNOWN_MUTEX` | the unrecognised mutex name from the triggering event. |
| `E_BLOCKED` | the mutex the task is queued behind. |
| `E_BUSY_TRY` | the held mutex the `try_acquire` was rejected against. |
| `E_IDLE` | the unowned mutex a `release` targeted. |
| `E_WRONG_OWNER` | the mutex whose `release` did not match the current owner. |
| `W_CYCLE` | the mutex on which the new wait edge closed a directed cycle (i.e. the mutex named in the blocking `acquire` event). |

`W_CYCLE` is co-emitted with the `E_BLOCKED` at the same `seq` and shares its `mutex` value; agents that emit `mutex: null` for `W_CYCLE` produce a mismatch.
