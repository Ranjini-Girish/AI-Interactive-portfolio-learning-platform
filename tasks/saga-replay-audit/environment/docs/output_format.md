# Output Format

Write `/app/output/saga_replay_audit.json` with 2-space indentation and a trailing newline.

## Top-level keys

`schema_version` (always `1`), `source_hashes`, `saga_audits`, `findings`, `summary`.

## source_hashes

Map relative paths `data/sagas/<filename>.json` to SHA-256 hex. Keys sorted alphabetically. Hash canonical file bytes: normalize CRLF to LF, strip one trailing newline if present.

## saga_audits

Array sorted by `saga_id`. Each entry:

- `saga_id`
- `events_kept`, `events_skipped`
- `steps_completed`, `steps_compensated`, `compensation_events`
- `avg_step_latency_ms` (float, 6 decimals)
- `integrity_lines` (integer count of hash lines for this saga)

## findings

All findings across sagas. Each finding:

- `finding_type`, `severity`, `severity_rank` (from policy)
- `saga_id`, `event_id` (nullable), `step` (nullable)
- `evidence` (object with finding-specific fields)

Sort findings by `(severity_rank ASC, finding_type ASC, saga_id ASC, event_id ASC, step ASC)` with nulls sorting before strings.

Per-saga `findings` arrays inside `saga_audits` are omitted; only the global `findings` list is used.

## summary

` saga_count`, `total_events_kept`, `total_events_skipped`, `total_findings`, `findings_by_type`, `findings_by_severity`, `avg_saga_latency_ms`, `integrity_hash`.
