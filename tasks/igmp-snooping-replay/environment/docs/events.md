# Events

`events.json` has the shape `{"events": [...]}`. Each entry MUST carry
a non-negative integer `seq` and a string `op`. The sequence is dense:
the first entry has `seq=0` and the i-th entry has `seq=i`. Any other
ordering is malformed and the binary MUST exit non-zero.

The set of allowed ops and their additional fields is closed:

| op | extra fields |
|---|---|
| `igmp_report`      | `port` (string), `group` (IPv4 string `224.0.0.0`–`239.255.255.255`), `vlan` (uint in `[1, 4094]`) |
| `igmp_leave`       | `port` (string), `group` (IPv4 string), `vlan` (uint in `[1, 4094]`) |
| `mcast_frame`      | `ingress_port` (string), `group` (IPv4 string), `vlan` (uint in `[1, 4094]`), `len` (uint in `[64, 9216]`) |
| `port_link_change` | `port` (string), `up` (bool) |
| `tick`             | `delta_sec` (positive integer) |

The `group` field is a canonical dotted-quad IPv4 string with no
leading zeros, and MUST be in the multicast range `224.0.0.0` through
`239.255.255.255`. The reserved local-network range `224.0.0.0/24`
(addresses `224.0.0.0` through `224.0.0.255`) is always flooded to
every port that allows the VLAN regardless of membership and MUST NOT
appear as a `group` field on `igmp_report` or `igmp_leave` events
(such events are malformed). On `mcast_frame`, link-local groups are
flooded but never tracked.

## Per-op state transitions

* **`igmp_report`** — sets
  `members[(vlan, group)][port] = {last_seen_time = now}`. If the
  port is a `router` port, the report is silently ignored (router
  ports do not register membership). If the port's `vlan` field
  doesn't match the event's `vlan`, the binary MUST exit non-zero
  (malformed). If the port-VLAN entry already exists with the same
  port, refresh `last_seen_time` and emit `W_REPORT_REFRESH`.

* **`igmp_leave`** — deletes
  `members[(vlan, group)][port]`. If `policy.fast_leave` is `true`
  and the port is a host port, the deletion happens immediately and
  emits `W_FAST_LEAVE`. Otherwise the deletion is conditioned on the
  port currently being in the membership: if it is not, emit
  `E_LEAVE_UNKNOWN_GROUP` and leave state unchanged. Router-port
  leaves are silently ignored.

* **`mcast_frame`** — see [`forwarding.md`](forwarding.md). Records a
  forwarding decision and never mutates the membership table.

* **`port_link_change`** — sets `link_state[port] = up`. If the new
  state equals the previous state (default `true`), emit `W_LINK_NOOP`
  and leave the membership table untouched. Otherwise update the link
  state. When the link transitions to `down`, every membership entry
  whose `port` equals this port is removed and a single
  `W_LINK_DOWN_PURGE` is emitted (with `name = port`).

* **`tick`** — advances `now` by `delta_sec`. Then ages out every
  `(vlan, group, port)` membership whose
  `(now - last_seen_time) > policy.ttl_sec`. Emit `W_MEMBER_AGED`
  once per aged entry, with `name` set to the entry's `port_id`.
  `tick` events MUST NOT cause forwarding decisions.

After each event is processed, the counters described in
[`output_format.md`](output_format.md) MUST be incremented.
