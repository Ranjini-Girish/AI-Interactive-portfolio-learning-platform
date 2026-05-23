# Diagnostic codes

The simulator emits diagnostics from the closed set below. Each code maps to
a fixed severity (`error` for every `E_*`, `warning` for every `W_*`, `note`
for every `N_*`). Each diagnostic record has the keys `account`, `code`,
`evidence`, `seq`, `severity` and `severity_rank` (the rank is looked up in
`policy.severity_ranks` by severity name).

## Per-event error codes (`severity = "error"`)

| Code | When | `evidence` keys |
| ---- | ---- | --------------- |
| `E_DAILY_LIMIT_EXCEEDED` | a `withdraw` (or the source leg of a `transfer`) would push that account's same-day running withdraw total above the active daily limit | `attempted_amount_cents`, `daily_total_after_cents`, `limit_cents` |
| `E_INSUFFICIENT_FUNDS` | a `withdraw`/source-`transfer`/`hold` would push `balance_cents - sum(active_holds)` below the account's overdraft floor — equivalently, `balance_cents - sum(active_holds) - attempted_amount_cents < floor_cents` | `attempted_amount_cents`, `available_cents`, `floor_cents` — where `available_cents` is the **post-op** available, i.e. `balance_cents - sum(active_holds) - attempted_amount_cents` (the same value the inequality tests against `floor_cents`); not the pre-op `balance_cents - sum(active_holds)` |
| `E_SELF_TRANSFER` | a `transfer` whose `target_account == account` while `policy.transfer_self_action == "error"` | empty object `{}` |
| `E_FROZEN_ACCOUNT` | the simulator rejects an event under `policy.frozen_account_action`; the `account` field of the diagnostic is the frozen account (which can be the source or target of a transfer) | empty object `{}` |
| `E_CLOSED_ACCOUNT` | same as above, but for a closed account, keyed on `policy.closed_account_action` (`block_all` rejects both source and target legs of a transfer; `allow_credits_only` rejects only debit legs against the closed account, so an inbound transfer leg succeeds while the outbound leg still emits the diagnostic) | empty object `{}` |
| `E_INVALID_REVERSAL` | a `reverse` cannot be applied; one of: target seq not present, target was a non-reversible op (`hold`/`release`/`reverse`), target outside the reversal window, target already reversed | `reverses_seq`, `reason` ∈ {`target_not_found`, `target_already_reversed`, `target_not_reversible`, `outside_window`} |

When an event is rejected by an error gate, the simulator skips the event
entirely (no money moves, no per-account counters change, no holds added or
released). Only one error diagnostic per event is emitted; gates are checked
in this order against the involved account(s):

1. Frozen / closed status gates (transfer checks both legs in source-then-target
   order; the first gate that rejects determines the emitted diagnostic and
   the `account` field is set to the rejecting account).
2. Self-transfer gate (only `transfer`).
3. Daily-limit gate (`withdraw` and source-`transfer` only).
4. Overdraft / insufficient-funds gate (`withdraw`, source-`transfer`, `hold`).
5. Reversal validity gate (`reverse` only; this gate is the *sole* gate run
   against a `reverse` event, so reversals neither check daily limits nor
   overdraft floors).

## Post-pass diagnostics

| Code | Severity | When | `seq` field | `account` field | `evidence` keys |
| ---- | -------- | ---- | ----------- | --------------- | --------------- |
| `W_HOLD_EXPIRED` | warning | once per still-active hold at trace end whose age `max_event_day - hold.day` exceeds `policy.hold_max_age_days` | `max_event_seq` (the `seq` of the last event in the trace) | the hold's owning account | `hold_seq`, `age_days`, `amount_cents` |
| `N_RECONCILIATION_MISMATCH` | note | once per account whose final `balance_cents` disagrees with `snapshots.expected_balances`; accounts missing from the snapshot map do NOT trigger this code | the `seq` of the last event in the trace | the mismatched account | `expected_balance_cents`, `actual_balance_cents`, `delta_cents` (= `actual - expected`) |

## Sort order

`event_diagnostics.json["diagnostics"]` is sorted by:

1. `severity_rank` ascending (more severe first).
2. `seq` ascending.
3. `code` ascending (ASCII).
4. `account` ascending (ASCII).
