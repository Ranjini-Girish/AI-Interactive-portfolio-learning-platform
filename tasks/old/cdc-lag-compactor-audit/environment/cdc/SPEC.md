# CDC Lag Compactor Audit Contract

This read-only dataset under `/app/cdc/` defines how five JSON reports must be written under `/app/audit/`. Every rule here is binding.

## Inputs

`pool_state.tsv` has one row `current_day|<int>`. `policy.tsv` rows are `tier|min_lag|max_lag|retention_days|merge_gap_lsn|max_tombstone_pct|risk_weight`. `streams.tsv` rows are `stream|tier|upstreams|declared_state`; upstreams are comma-separated or `-`. `partitions/<stream>.tsv` rows are `partition|last_source_lsn|last_sink_lsn|max_event_day`. `segments/<stream>-<partition>.tsv` rows are `segment_id|low_lsn|high_lsn|bytes|tombstones|checksum_family|max_event_day`. `incidents.tsv` rows are `event_id|kind|stream|partition|day|accepted|value_a|value_b`.

## Incident Filtering

An incident is accepted only when `accepted` is `true`, `day <= current_day`, `kind` is one of `late_arrival_grace`, `partition_rewind`, `compaction_hold`, `stream_compromise`, `force_replay`, or `source_pause`, the stream exists, and any non-`*` partition exists on that stream. `partition_rewind`, `compaction_hold`, `force_replay`, and `source_pause` require a concrete partition. For duplicate accepted events with the same kind and target, the event with the greatest day wins, with `event_id` ascending as the tie-break. All rejected rows are counted in `summary.ignored_incident_events`.

## Quarantine

Every stream with an accepted `stream_compromise` is directly quarantined. Quarantine propagates through `streams.tsv` from producer to every transitive consumer. Direct quarantine is reported as `direct`, propagated quarantine as `inherited`, and unaffected streams as `none`.

## Partition Lag

For each partition, `effective_sink_lsn` starts as `last_sink_lsn`; an accepted `partition_rewind` replaces it with the smaller of `last_sink_lsn` and `value_a`. `raw_lag = max(0, last_source_lsn - effective_sink_lsn)`. `event_lag_days = max(0, current_day - max_event_day - grace_days)`, where `grace_days` is the winning stream-level `late_arrival_grace` `value_a` or zero. Partition status precedence is `quarantined`, `replay_required`, `paused`, `stale`, `lagging`, `caught_up`. Quarantine wins first. `force_replay` or rewind makes `replay_required`. Active `source_pause` makes `paused` when `day <= current_day <= day + value_a - 1`. `stale` applies when `raw_lag > max_lag` or `event_lag_days > retention_days`; `lagging` applies when `raw_lag > min_lag` or `event_lag_days > 0`; otherwise `caught_up`.

Each partition row carries a `reasons` array with exactly one token chosen by the winning status: `stream_quarantine` for `quarantined`; `force_replay` when `replay_required` from an accepted `force_replay`, otherwise `rewind` when `replay_required` from an accepted `partition_rewind`; `source_pause` for `paused`; `lag_threshold` for `stale`; `within_recovery` for `lagging`; `within_floor` for `caught_up`.

## Stream Status And Risk

Stream status precedence is `quarantined`, `replay_required`, `degraded`, `healthy`. A stream is `replay_required` if any of its partitions are `replay_required` or `stale`. A stream is `degraded` if any partition is `lagging` or `paused`, or if any upstream stream is `quarantined` or `replay_required`; upstream degradation is propagated until stable but never overrides quarantine or replay. Risk rows are sorted by `risk_score` descending, then stream ascending. `risk_score` is `(sum raw_lag for stream * risk_weight) // 10`, plus 100 for direct quarantine, 80 for inherited quarantine, 25 for replay-required status, 10 for degraded status, and 15 for each quarantined direct upstream.

Each replay-risk row lists `reasons` in append order when the corresponding bonus applies: `quarantine` when stream status is `quarantined`; `replay` when stream status is `replay_required`; `degraded` when stream status is `degraded`; `upstream_quarantine` when `upstream_quarantine_count` is greater than zero. When no token was appended, `reasons` is exactly `["nominal"]`. `upstream_quarantine_count` is the count of upstream streams that are quarantined (directly or by inheritance).

## Compaction

For each partition, segments are sorted by `low_lsn`, then `segment_id`. Quarantined streams emit one `hold_quarantine` group per segment. Active `compaction_hold` emits one `hold_incident` group per segment when `day <= current_day <= day + value_a - 1`. Otherwise, adjacent segments merge while they share `checksum_family`, the next gap is at most `merge_gap_lsn`, and combined `tombstones * 100 <= bytes * max_tombstone_pct`. A group of two or more segments has action `merge` with reason `adjacent_eligible`. A single segment with `max_event_day <= current_day - retention_days` has action `evict` with reason `retention_expired`; every other single segment has action `keep` with reason `not_mergeable`. Quarantined streams emit `hold_quarantine` groups with reason `stream_quarantine`. Active `compaction_hold` emits `hold_incident` groups with reason `active_hold`.

## Outputs

Write five files under the audit directory. All JSON must be UTF-8, two-space indented, object keys sorted lexicographically at every level, and end with one trailing newline.

`partition_lag.json` is `{"partitions": [...]}` sorted by `stream` ascending, then `partition` ascending. Each row has `effective_sink_lsn`, `event_lag_days`, `partition`, `raw_lag`, `reasons` (one-element array per the Partition Lag section), `status`, and `stream`.

`compaction_plan.json` is `{"groups": [...]}` sorted by `stream`, then `partition`, then the first segment's `low_lsn` order within the partition. Each group has `action` (`hold_quarantine`, `hold_incident`, `merge`, `evict`, or `keep`), `bytes`, `output_high_lsn`, `output_low_lsn`, `partition`, `reason` (`stream_quarantine`, `active_hold`, `adjacent_eligible`, `retention_expired`, or `not_mergeable`), `segment_ids` (ordered as in the segment file), and `stream`.

`replay_risk.json` is `{"streams": [...]}` sorted by descending `risk_score`, then ascending `stream`. Each row has `reasons`, `risk_score`, `status` (stream status), `stream`, and `upstream_quarantine_count`.

`quarantine_graph.json` is `{"streams": [...]}` sorted by ascending `stream`. Each row has `inherited_from` (sorted upstream stream ids that caused inherited quarantine, empty when none), `quarantine_status` (`direct`, `inherited`, or `none`), and `stream`.

`summary.json` has `compaction_action_counts` (map from compaction `action` to count), `ignored_incident_events`, `partition_status_counts` (map from partition `status` to count), `stream_status_counts` (map from stream `status` to count), and `total_replay_risk` (sum of all `risk_score` values).
