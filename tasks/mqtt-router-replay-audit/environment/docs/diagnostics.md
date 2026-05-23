# Diagnostic codes

The diagnostic catalogue is **closed**. Any code outside this set is a
bug; the verifier rejects unknown codes.

## Severity ranks

| severity   | rank |
|------------|------|
| `error`    | 0    |
| `warning`  | 1    |
| `note`     | 2    |

Within an event the diagnostics array is sorted ascending by
`(severity_rank, code, client_id, topic, filter)`. Missing fields sort as
the empty string. The whole `diagnostics.events` array is sorted
ascending by `seq`, and only events that produced at least one diagnostic
appear (sparse list).

## Error codes (severity `error`)

| code                       | when                                                             | extra fields            |
|----------------------------|------------------------------------------------------------------|-------------------------|
| `E_DUPLICATE_CONNECT`      | `connect` for an `id` already in `connected[]`                   | `client_id`             |
| `E_NOT_CONNECTED`          | subscribe / unsubscribe / disconnect / expire_keepalive against an id not in `connected[]` | `client_id` |
| `E_INVALID_TOPIC`          | `publish` topic (or will topic on abrupt disconnect) is malformed | `topic` (and `client_id` for wills) |
| `E_INVALID_TOPIC_FILTER`   | `subscribe` filter is malformed or uses a disabled wildcard      | `client_id`, `filter`   |
| `E_SUBSCRIPTION_LIMIT`     | adding a new filter would exceed `policy.max_subscriptions_per_client` | `client_id`, `filter` |

## Warning codes (severity `warning`)

| code                  | when                                                          | extra fields  |
|-----------------------|---------------------------------------------------------------|---------------|
| `W_NO_SUBSCRIBERS`    | a `publish` (or will publish) had zero matching connected recipients | `topic` |
| `W_RETAINED_LIMIT`    | `retain=true` would add a new topic but the retained map is at `policy.max_retained` | `topic` |

## Note codes (severity `note`)

| code                  | when                                                              | extra fields |
|-----------------------|-------------------------------------------------------------------|--------------|
| `N_SESSION_FRESH`     | a `connect` produced a brand-new session (no persistent session was restored) | `client_id` |
| `N_SESSION_RESUMED`   | a `connect` with `clean_start = false` restored subs from `persistent_sessions[id]` | `client_id` |
| `N_WILL_DELIVERED`    | an abrupt disconnect (or `expire_keepalive`) had a valid-topic will and the broker published it | `client_id` |

## Per-event diagnostic structure

```json
{
  "seq": 17,
  "diagnostics": [
    {"client_id": "c-alpha", "code": "N_WILL_DELIVERED", "severity": "note"},
    {"code": "W_NO_SUBSCRIBERS", "severity": "warning", "topic": "status/alpha"}
  ]
}
```

Only the fields listed in the table for a given code appear -- never emit
`filter` on a `W_NO_SUBSCRIBERS`, etc. `code`, `severity`, and any
relevant id/topic/filter are the only allowed keys.
