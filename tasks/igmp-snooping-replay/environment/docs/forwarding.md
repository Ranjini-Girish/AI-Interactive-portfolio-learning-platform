# Multicast Frame Forwarding

This document specifies the deterministic algorithm applied to every
`mcast_frame` event.

## Step 0 — port and VLAN sanity

* If `ingress_port` is not in the configured `ports` set, the binary
  MUST exit non-zero (this is a malformed-input error, not a runtime
  diagnostic).
* If the ingress port's `vlan` does not equal the frame's `vlan`,
  emit `E_INGRESS_VLAN_MISMATCH` with `name = ingress_port`, record
  a `dropped` decision with `reason = "vlan_mismatch"`, and stop.
* If `link_state[ingress_port]` is `false`, emit
  `E_INGRESS_PORT_DOWN` with `name = ingress_port`, record `dropped`
  with `reason = "ingress_port_down"`, and stop.

## Step 1 — link-local groups (always flooded)

If `group` is in `224.0.0.0/24` (i.e. the first three octets are
`224.0.0`), the decision is **`flooded`**: the egress set is every
port whose link is up, whose `vlan` equals the frame's `vlan`, and
that is not the ingress port. Sort the egress port IDs ASCII
ascending. Do NOT consult the membership table for link-local groups.
No diagnostic is emitted.

## Step 2 — non-link-local groups

Compute the egress set as follows, sorted ASCII ascending and
excluding the ingress port:

* Every `router` port whose `vlan` equals the frame's `vlan` and whose
  link is up — *unconditionally*. Router ports always receive every
  multicast frame on their VLAN.
* Plus every `host` port that has registered membership for
  `(vlan, group)` (i.e. there is an entry in `members[(vlan, group)]`
  whose key is that port_id) AND whose link is up.

If the resulting egress set is empty AND `policy.drop_unknown_groups`
is `true`, the decision is `dropped` with `reason = "no_members"` and
emit `W_DROPPED_NO_MEMBERS` with `name = group`. If the resulting
egress set is empty AND `policy.drop_unknown_groups` is `false`, the
decision is `flooded` to every link-up port on the frame's VLAN
(excluding ingress) — this is the IGMP-snooping conservative fallback.

If the resulting egress set is non-empty, the decision is
**`forwarded`** if the egress set has exactly one entry, otherwise
**`flooded`**.

## Step 3 — record

If `policy.track_forwarding` is `true`, append the decision to
`forward_log.json` (see [`output_format.md`](output_format.md));
otherwise the file is exactly `{"forwards": []}`. Always increment the
`summary.totals` counters according to the decision (regardless of
`track_forwarding`).
