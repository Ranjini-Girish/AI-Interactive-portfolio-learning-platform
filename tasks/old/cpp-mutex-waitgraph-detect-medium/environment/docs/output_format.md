# Output format

Write five files under the output directory.

`mutex_state.json`: object with `mutexes` array sorted by `name`. Each mutex has `name` and `owner` (string or null).

`wait_edges.json`: object with `edges` array sorted by `(waiter, mutex)`. Each edge has `mutex`, `owner`, and `waiter` for every task still queued while the mutex has a non-null owner.

`action_log.json`: object with `actions` array in event order. Rows include successful `acquire` and `try_acquire` (`mutex`, `op`, `seq`, `task`, `tick`), `release` with the same fields, and `wake` rows emitted when a release hands the mutex to a queued waiter.

`diagnostics.json`: object with `events` array sorted by `seq`. Each element has `diagnostics` sorted by severity rank, then `code`, then `mutex` (null before strings).

`summary.json` counters: `acquires_blocked`, `acquires_succeeded`, `cycles_detected`, `releases`, `ticks`, `total_events`, `try_acquire_rejected`, `wakes_from_queue`.

All files canonical JSON: UTF-8, ASCII, 2-space indent, sorted keys, trailing newline.
