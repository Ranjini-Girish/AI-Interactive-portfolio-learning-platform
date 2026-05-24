# Saga Replay Specification

## Input

- Saga definitions: `/app/data/sagas/*.json`, each with `saga_id` and `events`.
- Policy: `/app/config/policy.json` for finding severities and severity ranks.

## Replay ordering

Within each saga, sort events by `(sequence ASC, timestamp_ms ASC)`.

## Deduplication

Walk the sorted list in order. The first occurrence of each `event_id` is kept; later rows with the same `event_id` are skipped and emit a `duplicate_event_skipped` finding (severity from policy).

## Timestamp consistency

After deduplication, scan the kept events in replay order. If any event has `timestamp_ms` strictly less than the previous kept event, emit `out_of_order_timestamp` for that event.

## Parent validation

For each kept event with non-null `parent_event_id`, the parent must refer to an `event_id` present among the kept events of the same saga. Otherwise emit `orphan_parent`.

## Step lifecycle

Process kept events in replay order:

- `started`: record that `step` was started.
- `completed`: mark `step` as completed (overwrites started).
- `compensated`: mark `step` as compensated (undoes a prior completion of that step).

A **stalled step** is a `step` that was started but never completed or compensated. Emit `stalled_step` for each stalled step name.

## Compensation ordering

Collect all kept events with `status == "compensated"`. They must be applied in **strictly decreasing** `sequence` order (highest sequence first). If the kept compensated events are not strictly decreasing by sequence when read in replay order, emit `compensation_order_violation`.

## Per-saga metrics

- `events_kept`: count of kept events.
- `events_skipped`: count of duplicate skips.
- `steps_completed`: distinct steps whose final state is completed.
- `steps_compensated`: distinct steps whose final state is compensated.
- `compensation_events`: count of kept events with status `compensated`.
- `avg_step_latency_ms`: harmonic mean of `duration_ms` over kept `completed` events where `duration_ms` is a positive integer. If none, `0.0`. Round to 6 decimals.

Harmonic mean of values `v_i`: `n / sum(1/v_i)`.

## Summary

- `saga_count`: number of sagas.
- `total_events_kept`, `total_events_skipped`, `total_findings`.
- `findings_by_type`, `findings_by_severity` (all five severity keys present, zero if none).
- `avg_saga_latency_ms`: harmonic mean of per-saga `avg_step_latency_ms` values that are `> 0`. Round to 6 decimals.

## Integrity hash

SHA-256 hex digest of UTF-8 text: one line per kept event across all sagas, sagas processed in ascending `saga_id`, events in replay order within saga:

`saga_id|event_id|sequence|status`

Join lines with `\n` (no trailing newline before hashing).
