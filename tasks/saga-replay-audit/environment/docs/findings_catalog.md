# Finding Types

| Type | When emitted |
|------|----------------|
| `duplicate_event_skipped` | Second+ row with same `event_id` after sort |
| `out_of_order_timestamp` | Kept event timestamp strictly before previous kept |
| `orphan_parent` | `parent_event_id` not among kept ids |
| `stalled_step` | Step ended in `started` state |
| `compensation_order_violation` | Compensated events not strictly decreasing by `sequence` in replay order |

Severities come from `/app/config/policy.json`.
