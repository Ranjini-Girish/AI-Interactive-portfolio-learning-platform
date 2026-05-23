# Diagnostics

The simulator emits a closed set of diagnostics into
`igmp_diagnostics.json`. Each diagnostic has these fields:

* `seq` — the `seq` of the event that triggered it.
* `severity` — one of `error`, `warning`, `note`.
* `code` — one of the codes below; nothing else is allowed.
* `name` — a non-null ASCII string identifying the affected entity
  (a `port_id`, an IPv4 `group` string, or `*` if not applicable).

`severity_rank` for sorting purposes: `error=3`, `warning=2`, `note=1`.

| code | severity | severity_rank | when emitted | `name` is |
|---|---|---|---|---|
| `E_INGRESS_PORT_DOWN`     | `warning` | 2 | `mcast_frame` whose ingress port link is down. The frame is dropped. | `ingress_port` |
| `E_INGRESS_VLAN_MISMATCH` | `warning` | 2 | `mcast_frame` whose `vlan` doesn't equal the ingress port's configured `vlan`. The frame is dropped. | `ingress_port` |
| `E_LEAVE_UNKNOWN_GROUP`   | `warning` | 2 | `igmp_leave` (host port, non-fast-leave path) for a `(vlan, group)` where the port is not currently a member. | `port` |
| `W_REPORT_REFRESH`        | `note`    | 1 | `igmp_report` from a port already a member of `(vlan, group)`. Refresh `last_seen_time`. | `port` |
| `W_FAST_LEAVE`            | `note`    | 1 | `igmp_leave` from a host port when `policy.fast_leave` is `true`. | `port` |
| `W_LINK_NOOP`             | `note`    | 1 | `port_link_change` whose new state equals the previous state of the port. | `port` |
| `W_LINK_DOWN_PURGE`       | `note`    | 1 | `port_link_change` from `up` to `down` that removed at least one membership entry. | `port` |
| `W_MEMBER_AGED`           | `note`    | 1 | `tick` that aged a particular `(vlan, group, port)` membership past `policy.ttl_sec`. | `port` |
| `W_DROPPED_NO_MEMBERS`    | `note`    | 1 | `mcast_frame` for a non-link-local group with no router or member ports under `policy.drop_unknown_groups=true`. | `group` |

Within a single `seq`, multiple diagnostics MAY be emitted; they are
written in the canonical sort order (`seq` ascending, then
`(severity_rank desc, code asc, name asc)`).

The four input documents and the four output documents form a closed
contract: any code not in this table is forbidden.
