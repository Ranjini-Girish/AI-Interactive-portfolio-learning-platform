# CIDR notes

This task is IPv4-only. Every rule CIDR and every flow IP is in dotted-quad form.

## Normalization

A CIDR with host bits set must be normalized by clearing them. Equivalent expressions:

| Literal | Canonical |
|---|---|
| `0.0.0.0/0` | `0.0.0.0/0` |
| `10.0.20.0/24` | `10.0.20.0/24` |
| `10.0.20.5/24` | `10.0.20.0/24` |
| `192.168.10.42/16` | `192.168.0.0/16` |
| `203.0.113.5/32` | `203.0.113.5/32` |

`/32` is a single host. `/0` is the universe of IPv4 addresses.

## Containment

`flow.src_ip ∈ CIDR(rule.source)` if and only if `flow.src_ip` (treated as a 32-bit integer) lies in the network described by the canonical CIDR. The same applies to destination IPs.

## The literal `"any"`

`"any"` is a sentinel that matches every IPv4 address. It is **not** a CIDR. Models that try to convert `"any"` to a CIDR like `0.0.0.0/0` will produce the same result for source/destination matching, but will fail consistency checks elsewhere if they propagate the conversion.

## Invalid CIDRs

A `source` or `destination` that is neither `"any"` nor a parseable IPv4 CIDR makes the rule unsatisfiable (status `"unreachable"`).
