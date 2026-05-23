# Event semantics

Events are sorted by `seq` ascending and then applied in that order. The
sequence numbers must be **dense** -- exactly `0..N-1`. A non-dense or
duplicate `seq` is malformed input and the binary must exit non-zero.

Every event has at least these two fields:

* `seq` (integer, >= 0)
* `kind` (one of: `tick`, `connect`, `disconnect`, `expire_keepalive`,
  `subscribe`, `unsubscribe`, `publish`)

The remaining fields depend on the kind.

## `tick`

```json
{"seq": 0, "kind": "tick", "delta_sec": 5}
```

Advances the global clock: `now_sec += delta_sec`. No other state changes,
no `session_log` entry, no diagnostics. `delta_sec` must be non-negative.

## `connect`

```json
{"seq": 7, "kind": "connect", "id": "c1",
 "clean_start": false, "keep_alive_sec": 60,
 "will": {"topic": "t/will", "payload_id": 9, "qos": 1, "retain": false}}
```

* If `id` is already in `connected[]`: emit `E_DUPLICATE_CONNECT` and
  abandon the event (no other state mutates, no `session_log` entry, no
  will is attached).
* Else, if `clean_start = true`: drop any matching `persistent_sessions[id]`
  entry and create a fresh non-persistent client with empty subs. Append
  `{"action": "fresh", ...}` to `session_log` and emit `N_SESSION_FRESH`.
* Else (`clean_start = false`): if `persistent_sessions[id]` exists, restore
  its subs into a new persistent connected client (`N_SESSION_RESUMED`,
  `action: "resumed"`); otherwise create a fresh persistent connected
  client with empty subs (`N_SESSION_FRESH`, `action: "fresh"`).

The `will` (optional) is stored on the client and is consumed only by
`expire_keepalive` or by `disconnect` with `abrupt = true`.

## `disconnect`

```json
{"seq": 9, "kind": "disconnect", "id": "c1", "abrupt": false}
```

* If `id` is not currently connected: emit `E_NOT_CONNECTED` and stop.
* Else, if `abrupt = true` and the client has a will, the broker delivers
  the will exactly like a `publish` (same matching, same retain rules).
  When the will topic is malformed it emits `E_INVALID_TOPIC`; when it is
  delivered (regardless of whether anyone matched) it emits
  `N_WILL_DELIVERED`. Will retain follows the same rules as publish retain.
* The client is removed from `connected[]`. If it was persistent, its subs
  are saved into `persistent_sessions[id]`. If it was not persistent, its
  state is dropped entirely.
* Append a `disconnect` entry to `session_log` with `abrupt` and the
  computed `session_kept` boolean.

`abrupt` defaults to `false` if omitted.

## `expire_keepalive`

```json
{"seq": 11, "kind": "expire_keepalive", "id": "c1"}
```

Identical to a `disconnect` with `abrupt = true`. The `session_log` entry
uses `kind: "expire_keepalive"` and always has `abrupt = true`.

## `subscribe`

```json
{"seq": 4, "kind": "subscribe", "client_id": "c1",
 "filter": "sensors/+/temp", "qos": 1}
```

* If `client_id` is not connected: emit `E_NOT_CONNECTED` and stop.
* Else, if `filter` is invalid (see `wildcards.md`): emit
  `E_INVALID_TOPIC_FILTER` and leave subs unchanged.
* Else, if the filter is brand-new for this client and adding it would
  push the client's sub count above `policy.max_subscriptions_per_client`:
  emit `E_SUBSCRIPTION_LIMIT` and leave subs unchanged. A re-subscribe to
  an already-present filter is allowed even when the cap would otherwise
  be hit; it just mutates the qos.
* Else add or overwrite the entry, then push every retained message whose
  topic matches `filter` to this client (one `delivery_log` entry per
  retained-topic match, single recipient, `delivered_qos = min(retained_qos,
  sub_qos)`, `publish_qos = retained_qos`).

## `unsubscribe`

```json
{"seq": 6, "kind": "unsubscribe", "client_id": "c1", "filter": "sensors/+/temp"}
```

* If `client_id` is not connected: emit `E_NOT_CONNECTED` and stop.
* Else remove `filter` from this client's subs (no-op if it was not
  subscribed). No diagnostic on a no-op.

## `publish`

```json
{"seq": 1, "kind": "publish", "topic": "sensors/A/temp",
 "payload_id": 11, "qos": 1, "retain": false, "client_id": "c-alpha"}
```

* If `topic` is invalid (see `wildcards.md`): emit `E_INVALID_TOPIC` and stop.
* Else add `topic` to `topics_published`, then walk every connected client.
  For each client `c` whose `subs` contain at least one filter matching
  `topic`, compute `delivered_qos = min(publish_qos, max_matching_sub_qos)`
  and add one recipient `{client_id: c, delivered_qos: ...}`. If the
  publishing `client_id` itself matches and `policy.deliver_to_self =
  false`, that client is skipped.
* If at least one recipient is selected, increment `publishes_delivered`
  and `deliveries_total`. Otherwise emit `W_NO_SUBSCRIBERS`.
* Append the delivery (with whatever recipients list, possibly empty) to
  `delivery_log.deliveries`.
* If `retain = true`, apply retained-update rules from `output_format.md`
  (clear when `payload_id == 0` and `qos == 0`; otherwise overwrite, with
  `W_RETAINED_LIMIT` if the topic is brand-new and the map is full).

`client_id` on a `publish` is optional; when omitted, no client is treated
as the publisher (so `deliver_to_self = false` has no effect).
