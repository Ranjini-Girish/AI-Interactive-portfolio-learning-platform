# Ingest watermark skew audit (normative)

All inputs are UTF-8 JSON. The audit day is `pool_state.current_day` (integer). Never mutate anything under `/app/ingest_buffers/`.

## Ingest window

Let `I = policy.ingest_window_days` (integer ≥ 1). Only batch files whose `ingest_day` satisfies `current_day - (I - 1) <= ingest_day <= current_day` are processed. Events inside ignored batches are absent from every output.

Each batch file lives at `batches/<batch_id>.json` with fields `batch_id`, `partition_id`, `ingest_day`, and `events` (array).

Each event object requires `event_id` (string), `event_day` (integer), `idempotency_key` (string), `sequence` (integer ≥ 0), and `bytes_hint` (integer ≥ 0).

Partitions name `partitions/<partition_id>.json` with `partition_id` and `source_id`. Sources name `sources/<source_id>.json` with `source_id` and `tier` ∈ {`gold`,`silver`,`bronze`}.

## Incidents

Read `incident_log.events`. Keep only events with `accepted == true` and `day <= current_day`. Sort kept events by ascending `(day, event_id)` and process in that order to build running adjustments.

Supported `kind` values:

- `lateness_delta`: fields `target_tier` ∈ {`gold`,`silver`,`bronze`} and integer `delta`. Adds `delta` to the running lateness allowance for that tier (additive).
- `dedup_window_extend`: integer `delta`. Adds `delta` to the running dedup window width (additive).
- `grace_day`: fields `partition_id` and integer `extra_days`. While processing events on that `partition_id` with `ingest_day >=` the incident `day`, add `extra_days` to the lateness allowance for that partition only (additive across multiple grace incidents).
- `source_compromise`: field `source_id`. After this incident is applied, every event whose partition maps to that `source_id` and whose `ingest_day >=` the incident `day` must emit disposition `rejected_quarantine` before any lateness or dedup logic.

Malformed incidents (unknown `kind`, wrong types, missing required fields) are ignored and counted in `summary.ignored_incident_events`.

## Per-event disposition

Process eligible events in ascending order of `(partition_id, ingest_day, sequence)` (ASCII `partition_id`).

For each event compute `lateness_allowance = policy.lateness_days_by_tier[tier] + tier_lateness_delta[tier] + partition_grace_extra[partition_id]` where `partition_grace_extra` sums every applied `grace_day.extra_days` for that partition whose incident `day <= ingest_day`.

Effective dedup width is `policy.dedup_window_days + dedup_window_delta_sum`.

1. If the event's source is compromised and `ingest_day >= compromise_day`, disposition `rejected_quarantine`.
2. Else if `event_day < current_day - lateness_allowance`, disposition `rejected_stale`.
3. Else if an earlier kept event shares the same `(source_id, idempotency_key)` and `abs(event_day - kept.event_day) <= effective dedup width`, compare tuples `(event_day, sequence)` lexicographically. The lesser tuple becomes `duplicate_superseded`; the greater becomes `accepted` (replacing the prior kept row). Record each supersession in `dedup_journal`.
4. Else disposition `accepted`.

Only `accepted` events participate in partition skew and watermark math.

## Partition watermark and skew

For each partition, collect accepted `event_day` values. If none, emit `watermark_day` null, `skew_exceeded` false, and zero accepted counters.

Otherwise let `min_d` and `max_d` be the min and max accepted `event_day`. If `max_d - min_d > policy.skew_guard_days`, set `skew_exceeded` true and `watermark_day = max_d - policy.skew_penalty_days`; else `skew_exceeded` false and `watermark_day = max_d - policy.watermark_retreat_days`.

## Partition reasons

When `skew_exceeded` is true, include `skew_exceeded` in `reasons`. When any `rejected_quarantine` events exist for the partition, include `source_quarantine`. When any `rejected_stale`, include `stale_events_present`. When any `duplicate_superseded`, include `dedup_superseded`. `reasons` must be strictly increasing ASCII, unique. Empty list when none apply.

## Source verdicts

If a kept `source_compromise` names the source, `disposition` is `quarantined` and `reasons` is `["source_compromise"]`. Otherwise `disposition` is `active` and `reasons` is `[]`. `accepted_events` counts accepted events for that source across all partitions.

## Outputs (five files under `/app/audit/`)

Canonical JSON: UTF-8, two-space indent, ASCII only, object keys sorted lexicographically at every object depth, colon plus single space, no trailing spaces on lines, exactly one trailing newline at EOF.

### partition_ledger.json

- `partitions`: array sorted by ascending `partition_id`. Each object: `partition_id`, `source_id`, `watermark_day` (int or null), `accepted_count`, `rejected_stale_count`, `rejected_quarantine_count`, `duplicate_superseded_count` (all ints), `skew_exceeded` (bool), `reasons` (array of strings).

### source_verdicts.json

- `sources`: array sorted by ascending `source_id`. Each object: `source_id`, `tier`, `disposition` (`active`|`quarantined`), `accepted_events` (int), `reasons` (array).

### dedup_journal.json

- `supersessions`: array sorted by ascending `(source_id, idempotency_key, superseded_event_id)`. Each object: `source_id`, `idempotency_key`, `superseded_event_id`, `kept_event_id`.

### incident_journal.json

- `applied_events`: array in ascending `(day, event_id)` order with `day`, `event_id`, `kind`, and kind-specific optional fields sorted inside each object.

### summary.json

Fields: `applied_incident_events`, `ignored_incident_events`, `sources_total`, `partitions_total`, `quarantined_sources`, `total_accepted`, `total_duplicate_superseded`, `total_rejected_stale`, `total_rejected_quarantine`, `partitions_with_skew_exceeded` (all ints except counts are ints; `quarantined_sources` and `partitions_with_skew_exceeded` are ints).
