# Output sort order

Every array in the five output files has a fixed sort order. Apply each sort to the final array contents (after all simulation work is done); canonical JSON formatting does not re-sort array elements.

| File | Array | Sort key |
|------|-------|----------|
| `mutex_state.json` | `mutexes` | `name` ascending. |
| `wait_edges.json` | `edges` | `(waiter, mutex)` lexicographic ascending. |
| `action_log.json` | `actions` | `seq` ascending (ties resolve to insertion order, but a `release` and its `wake` always carry the same `seq` and the `wake` row follows the `release`). |
| `diagnostics.json` | `events` | `seq` ascending. |
| `diagnostics.json` | `events[i].diagnostics` | `(severity_rank, code, mutex)` ascending, where severity rank is `error=0 < warning=1 < note=2`; among equal severity and code, an entry with `mutex == null` precedes any entry with a string `mutex`, and string mutexes sort lexicographically. |

Object keys at every depth in every file are independently sorted lexicographically; see `canonical_json.md`.
