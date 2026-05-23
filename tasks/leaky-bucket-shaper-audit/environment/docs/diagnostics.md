# Diagnostics

Each diagnostic record is `{ "seq": <int>, "code": <string>,
"severity": <string>, "bucket_id": <string>, "detail": <string> }`.
`bucket_id` is `""` when no bucket context applies.

## Closed code set

| Code                  | Severity | Trigger                                                     | Detail payload                              |
|-----------------------|----------|-------------------------------------------------------------|---------------------------------------------|
| `E_UNKNOWN_BUCKET`    | error    | `submit` references a bucket not in `buckets.json`          | `""`                                        |
| `W_DROPPED_OVERFLOW`  | warn     | `submit` rejected because admit would exceed capacity       | `size_bytes` as a decimal string            |
| `W_CAPACITY_REDUCED`  | warn     | `reconfigure` shrunk capacity below the current level       | `"<old_level>-><new_capacity>"`             |
| `W_RECONFIG_NOOP`     | warn     | `reconfigure` did not change capacity or leak rate          | `bucket_id` string                          |
| `N_ADMITTED`          | note     | `submit` admitted into a bucket                             | `size_bytes` as a decimal string            |

`severity_rank`: `error=3`, `warn=2`, `note=1`.

## Sort order in `shaper_diagnostics.json`

`(seq asc, severity_rank desc, code asc, bucket_id asc, detail asc)`.

The simulator only ever emits codes from this table.
