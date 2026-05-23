# IGMPv2 Snooping Replay — Overview

This task asks you to build a deterministic C++17 simulator of an
Ethernet switch's IGMPv2 snooping table. The switch tracks per-VLAN
multicast group membership by snooping IGMP `report` and `leave`
messages from hosts, ages members out when their TTL elapses, and
forwards multicast frames only to ports that have asked for the group
(plus router ports, which always receive every multicast).

State carried across the trace:

* `members`: a map keyed by `(vlan, group)` whose value is a map from
  `port_id` to `{last_seen_time}`.
* `link_state`: a map from `port_id` to a boolean `up` flag (default
  `true`).
* `now`: a monotonically non-decreasing integer clock (seconds), starts
  at `0` and advances only via `tick` events.

Ports are configured statically in `ports.json`. Each port has a
`port_id`, a `vlan` in `[1, 4094]`, and a `role` of either `"host"`
(participates in IGMP) or `"router"` (always receives every multicast
frame on its VLAN, regardless of explicit membership). The set of
`port_id` strings is fixed at start: events that reference a `port_id`
not in this set are errors.

For every event in `events.json` (in `seq` order, starting at `0`
with no gaps), apply the appropriate state transitions described in
[`events.md`](events.md), emit the diagnostics described in
[`diagnostics.md`](diagnostics.md), and (when the event is an
`mcast_frame`) record a forwarding decision following the rules in
[`forwarding.md`](forwarding.md).

When the trace terminates, write the four output files described in
[`output_format.md`](output_format.md).

## Entry points

* The binary is invoked as `/app/build/igmpsnoop IN_DIR OUT_DIR`. It
  reads `IN_DIR/{ports,events,policy}.json` and writes the four
  documented files into `OUT_DIR/`.
* It must not write anywhere else on the filesystem and must treat
  `IN_DIR/` (and `/app/build/`) as immutable for the duration of the
  run.

The four input documents, the diagnostic codes, and the four output
documents form a *closed contract*: any field, op, or code that is not
documented here is forbidden.
