# Output format

The binary writes exactly five files to the directory passed as
`argv[2]`. No other files. Every file is canonical JSON:

* UTF-8 encoded, but **all bytes <= 0x7F**: any non-ASCII codepoint must
  be emitted as a `\uXXXX` escape.
* Two-space indentation.
* Object keys lexicographically sorted at every depth.
* A single trailing `\n` (one byte, exactly).
* No extra whitespace anywhere (no `,` followed by space, etc., other
  than what `nlohmann::json::dump(2, ' ', true)` produces).

## `policy.json` reference

```json
{
  "now_sec": 1000,
  "max_subscriptions_per_client": 8,
  "max_retained": 6,
  "wildcard_plus_allowed": true,
  "wildcard_hash_allowed": true,
  "deliver_to_self": false
}
```

* `now_sec` -- starting wall clock; `tick.delta_sec` adds to it.
* `max_subscriptions_per_client` -- hard cap on `len(client.subs)`.
* `max_retained` -- hard cap on `len(retained)` for **new** topics.
* `wildcard_plus_allowed` / `wildcard_hash_allowed` -- when false, that
  wildcard token is rejected with `E_INVALID_TOPIC_FILTER`.
* `deliver_to_self` -- when false, a publishing client is excluded from
  its own publish's recipient list (only relevant when `client_id` is set
  on the publish).

## `broker_state.json`

```json
{
  "clients": [
    {"id":"c-alpha","keep_alive_sec":60,"persistent":true,
     "subscriptions":[{"filter":"sensors/+/temp","qos":1}, ...]}
  ],
  "now_sec": 1015,
  "persistent_sessions": [
    {"client_id":"c-bravo",
     "subscriptions":[{"filter":"control/cmd","qos":1}]}
  ],
  "retained": [
    {"payload_id":100,"qos":1,"retained_at_sec":0,"topic":"sensors/A/temp"}
  ]
}
```

Sort orders:

* `clients[]` ascending by `id`; per-client `subscriptions[]` ascending
  by `filter`.
* `persistent_sessions[]` ascending by `client_id`; per-session
  `subscriptions[]` ascending by `filter`.
* `retained[]` ascending by `topic`.

`now_sec` is the value after the last event was applied.

## `delivery_log.json`

```json
{
  "deliveries": [
    {"payload_id":11,"publish_qos":1,
     "recipients":[{"client_id":"c-alpha","delivered_qos":1}],
     "seq":1,"topic":"sensors/A/temp"}
  ]
}
```

* One entry per delivery occasion. A `publish` event always produces
  exactly one entry (even when `recipients` is empty). A successful
  `subscribe` produces zero or more entries -- one per matching retained
  topic.
* Outer sort: ascending by `(seq, topic)`. Inner `recipients` sort:
  ascending by `client_id`. Each recipient appears at most once per
  delivery (the broker collapses multi-filter matches into a single
  recipient with the maximum delivered_qos).

## `session_log.json`

```json
{
  "events": [
    {"action":"resumed","client_id":"c-charlie","kind":"connect","seq":5},
    {"abrupt":true,"client_id":"c-bravo","kind":"expire_keepalive",
     "seq":9,"session_kept":false},
    {"abrupt":true,"client_id":"c-alpha","kind":"disconnect",
     "seq":17,"session_kept":true}
  ]
}
```

* Strict trace order; the array is **not** independently sorted.
* `connect` entries always carry `action`. `disconnect` and
  `expire_keepalive` entries always carry `abrupt` and `session_kept`.
* No entry for events that emitted `E_DUPLICATE_CONNECT` or
  `E_NOT_CONNECTED`.

## `diagnostics.json`

```json
{
  "events": [
    {"diagnostics":[{"code":"...","severity":"...", ...}], "seq":17}
  ]
}
```

See `diagnostics.md` for the closed code set, sort order, and
per-code field set.

## `summary.json`

```json
{
  "active_clients": 3,
  "deliveries_total": 7,
  "diagnostics_by_code": {"E_DUPLICATE_CONNECT": 1, "...": 0},
  "events_total": 36,
  "persistent_sessions": 2,
  "publishes_delivered": 6,
  "retained_count": 6,
  "topics_published": ["sensors/A/temp", "..."]
}
```

* `active_clients` -- final size of `connected[]`.
* `events_total` -- length of `events.json`.
* `publishes_delivered` -- number of delivery_log entries that had at
  least one recipient (publish-driven entries with empty recipients do
  **not** count).
* `deliveries_total` -- sum of recipient counts over all delivery_log
  entries.
* `retained_count` -- final size of the retained map.
* `persistent_sessions` -- `len(persistent_sessions) + sum(1 for c in
  connected if c.persistent)`.
* `diagnostics_by_code` -- map from emitted diag code to count. Codes
  that never fired are absent (no zero entries).
* `topics_published` -- ASCII ascending list of every distinct topic that
  was the `topic` field of a successful (non-malformed) `publish` event.
  Will-publishes do not contribute.
