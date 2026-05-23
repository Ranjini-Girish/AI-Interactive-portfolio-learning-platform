# Matching semantics

A rule `R` matches a flow `F` if and only if every gate below succeeds.

## 1. Predicate satisfiability

If `R.source` or `R.destination` is not a valid CIDR (or `"any"`), the rule matches nothing. If `R.src_ports` or `R.dst_ports` is a list whose every range has `start > end`, the rule matches nothing. Empty port-range lists also match nothing.

## 2. Direction

When `policy.enable_directionality == true`, `R.direction` must equal `F.direction`. Otherwise direction is ignored everywhere — including in `matched_flows`, `flow_verdicts`, `escalation_warnings`, and `equivalence_classes`.

## 3. Source / destination CIDR

Source and destination CIDRs are normalized by clearing host bits before comparison. `10.0.20.5/24` is equivalent to `10.0.20.0/24` and `192.168.10.42/16` is equivalent to `192.168.0.0/16`. A literal IP must lie within the normalized network.

The string `"any"` matches every IPv4 address. There is no IPv6 in this task.

## 4. Protocol

`R.protocol == "any"` matches any flow protocol. Otherwise `R.protocol` must equal `F.protocol`.

## 5. Ports — TCP/UDP only

Ports are evaluated only when `F.protocol` is `"tcp"` or `"udp"`. For ICMP flows (and any other non-TCP/UDP protocol), `R.src_ports` and `R.dst_ports` are ignored entirely. Even a rule that specifies `protocol == "icmp"` and `dst_ports == [{"start": 80, "end": 80}]` matches every ICMP flow that passes gates 1–4.

When ports are evaluated, `R.src_ports == "any"` matches any source port; otherwise `F.src_port` must lie in some `[start, end]` range listed (inclusive). The same rule applies to destination ports. Ranges with `start > end` are silently skipped.
