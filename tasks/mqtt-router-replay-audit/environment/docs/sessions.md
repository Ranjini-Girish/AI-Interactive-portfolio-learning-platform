# Sessions, persistence, and will messages

The broker tracks two disjoint per-id collections:

1. `connected[id]` -- currently connected clients with subs, will, and
   keep-alive metadata.
2. `persistent_sessions[id]` -- saved subs from clients that disconnected
   while their `persistent` flag was `true`.

A given `id` is in exactly one of those at any moment (or in neither).

## Initial state from `clients.json`

For every entry in `clients.json`:

* `connected = true` (or omitted): goes into `connected[]` with the
  declared `persistent` flag, `keep_alive_sec`, and optional `will`.
* `connected = false`: must have `persistent = true`. Goes into
  `persistent_sessions[]` with empty subs.

A `connected = false` entry that also says `persistent = false` is
malformed input and the binary must exit non-zero. Duplicate `id`
entries are also malformed.

## `subscriptions.json` resolution

Each subscription's `client_id` is looked up in **both** collections, in
that order. If the id is in `connected[]`, the sub is attached to the
connected client. If the id is in `persistent_sessions[]`, the sub is
attached to the saved session. An id that is in neither is malformed
input.

## Persistent vs clean lifecycle

| Pre-state                | Event              | Post-state              | Diagnostic              | session_log action |
|--------------------------|--------------------|-------------------------|-------------------------|--------------------|
| connected[id] present    | `connect id`       | unchanged               | `E_DUPLICATE_CONNECT`   | (no entry)         |
| nothing for id           | `connect id` clean | new non-persistent      | `N_SESSION_FRESH`       | `fresh`            |
| nothing for id           | `connect id` !clean| new persistent (empty)  | `N_SESSION_FRESH`       | `fresh`            |
| persistent_sessions[id]  | `connect id` clean | new non-persistent (sessn dropped) | `N_SESSION_FRESH` | `fresh`     |
| persistent_sessions[id]  | `connect id` !clean| new persistent (subs restored) | `N_SESSION_RESUMED` | `resumed`     |

`!clean` is `clean_start = false`.

## Disconnect / expire_keepalive

`expire_keepalive` is identical to `disconnect` with `abrupt = true`,
except the `session_log` entry's `kind` reflects the actual event kind.
The processing order is fixed:

1. If `id` is not in `connected[]`: emit `E_NOT_CONNECTED`, stop.
2. Compute `abrupt = (kind == "expire_keepalive") OR ev.abrupt`.
3. If `abrupt` and the client has a will:
   - If the will topic is invalid: emit `E_INVALID_TOPIC` and skip the
     will publish.
   - Else publish the will (same matching, same `deliver_to_self` policy
     using the disconnecting client as sender, same retain rules), then
     emit `N_WILL_DELIVERED`.
4. Remove the client from `connected[]`. If `client.persistent` is true,
   save its subs into `persistent_sessions[id]` (overwriting any prior
   entry); otherwise drop the state entirely.
5. Append a `session_log` entry with `seq`, `kind`, `client_id`, the
   computed `abrupt`, and `session_kept = client.persistent`.

A non-abrupt disconnect with a will simply discards the will -- nothing
is published, no diagnostic is emitted.
