# Edge cases

The dataset is engineered around several adversarial cases. The contract enumerates each case explicitly so the only correct implementation is the one in `instruction.md`.

## Composite shadow

A rule may have `matched_flows` covered by the *union* of multiple higher-priority rules but not by any single one. The shadowed rule still receives status `shadowed`, with `shadowed_by` containing every rule needed in a minimum cover (lex-smallest tiebreak).

## Excluded port boundary

Port ranges are inclusive: `{"start": 1024, "end": 65535}` admits port `1024` and excludes port `1023`. A flow with `src_port == 1023` does not match a rule with `src_ports == [{"start": 1024, "end": 65535}]`, even by one port.

## ICMP ignores ports

For ICMP flows, both `src_ports` and `dst_ports` rule fields are ignored. A rule like `protocol == "icmp"` with `dst_ports == [{"start": 80, "end": 80}]` matches every ICMP flow that passes the other gates.

## Non-canonical CIDR

A rule with `source == "10.0.20.5/24"` must be normalized to `10.0.20.0/24` before comparison. Treating the `/24` as a `/32` host route would be wrong.

## Default-action redundancy

A deny rule whose flows would default-deny if the rule were removed is `redundant` even when it actually fires today. Compare verdicts using `policy.default_action` to substitute for the `"default"` tag.

## Direction-mismatched flows

When `enable_directionality == true`, an ingress rule never matches an egress flow and vice versa. Both `matched_flows` and the verdict computation respect this.

## Catch-all rules and `default_action_uses`

If a low-priority catch-all deny absorbs every otherwise-unmatched ingress flow, `default_action_uses` is `0`. Removing the catch-all would push those flows to `default`, raising the count.

## Pre-redundancy filtering of escalation warnings

A redundant deny rule produces no `escalation_warnings` even when an earlier allow shares its `matched_flows`. The same applies to unreachable denies.

## Equivalence-class strictness

The `(verdict, matched_rule_id)` invariance for `equivalence_classes` is stricter than the verdict-only invariance for `redundant`. A rule that is `redundant` may still be retained by `equivalence_classes` because its removal would change `matched_rule_id` for some flow.
