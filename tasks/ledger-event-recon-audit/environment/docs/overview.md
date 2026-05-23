# Ledger Auditor — Overview

This benchmark simulates an event-sourced banking ledger replay. The auditor
consumes a chronological trace of monetary events and produces four canonical
JSON reports describing the final account state, every diagnostic emitted
along the way, a snapshot reconciliation, and aggregate compliance counts.

## Inputs

The container ships four input files under `/app/data/`:

* `accounts.json` — `{"accounts": [...]}` — the static account directory.
* `events.json`   — `{"events": [...]}` — the chronological trace.
* `snapshots.json` — `{"expected_balances": {<account_id>: <int_cents>}}`
  — the closing balance the operator expects, used solely for reconciliation.
* `policy.json`   — runtime tunables (limits, gates, severity ranks).

See `field_schemas.md` for every field of every record.

## Simulator at a glance

The simulator processes `events.json` in strict ascending `seq` order. The
binary must sort the events by `seq` itself before replay — the physical
order of the array in `events.json` is not guaranteed to match `seq` order
and is not authoritative; the only ordering key is the `seq` field. Do not
emit a fatal error or refuse to run when the input array is unsorted; just
sort it. The simulator then keeps a small piece of per-account state:

* `balance_cents` — signed integer.
* `holds` — list of currently-active holds, each `{seq, amount_cents, day}`.
* `daily_withdraws` — running totals of withdraw legs keyed by `day`.
* `total_deposits_cents`, `total_withdrawals_cents` — sum of legs that
  *actually moved money* (so a successful `transfer` increments both, and a
  successful `reverse` increments the inverse legs too).
* `n_reversed_events` — count of events targeting this account that were
  themselves the target of a successful `reverse`.
* a small reversal-target index used to detect already-reversed targets.

Holds reduce the *effective* balance used by overdraft checks; they do not
reduce `balance_cents`. A `release` whose `reverses_seq` does not match an
active hold on the same account is a silent no-op (no diagnostic).

After the trace, two post-pass diagnostics are emitted:

* `W_HOLD_EXPIRED` — once per still-active hold whose age
  `max_event_day - hold.day` exceeds `policy.hold_max_age_days`.
* `N_RECONCILIATION_MISMATCH` — once per account whose final balance disagrees
  with `snapshots.expected_balances`. Accounts missing from the snapshot map
  are reconciled as `"unsnapshotted"` and emit no diagnostic.

## Outputs

Four canonical JSON files written to `/app/output/`:

* `account_state.json` — final per-account state.
* `event_diagnostics.json` — every diagnostic emitted, sorted.
* `reconciliation_report.json` — per-account expected vs actual balance.
* `compliance_summary.json` — aggregate severity histogram + totals.

`output_format.md` documents the exact shape of each.

## Build & run

The agent must author its own C++17 sources under `/app/src/` (and headers
under `/app/include/`), compile to `/app/build/ledgeraudit`, and invoke

    /app/build/ledgeraudit /app/data /app/output
