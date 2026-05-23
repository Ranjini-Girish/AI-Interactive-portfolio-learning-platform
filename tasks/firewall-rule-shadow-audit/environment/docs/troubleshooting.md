# Troubleshooting

When an output file fails an exact-match check, the most common causes are:

- **Wrong evaluation order.** Re-derive the order from `policy.tie_breaker`. `priority_lowest_wins` reverses the priority sort.
- **Treating ICMP like TCP.** ICMP flows ignore rule port specifications. Adding port checks for ICMP yields too few `matched_flows` and may flip a status from `shadowed` to `effective`.
- **Pairwise-only shadow check.** Composite shadows require checking unions, not pairs. A rule whose flows are covered only by the union of two higher rules must still be `shadowed`.
- **Verdict-only equivalence-class check.** `equivalence_classes` requires `(verdict, matched_rule_id)` invariance. Comparing only verdicts produces a smaller, but incorrect, removed list.
- **Default-action confusion.** When a rule's removal would push flows to the `"default"` tag, treat that tag as `policy.default_action` for the redundancy check (and only for redundancy).
- **CIDR host bits.** `10.0.20.5/24` is `10.0.20.0/24` after normalization. Comparing as `/32` will under-match flows.
- **Off-by-one ports.** Port ranges are inclusive on both ends. A flow on the boundary either fully matches or fully misses; there is no fractional match.
- **Lex-smallest cover.** When multiple minimum-cardinality covers exist for `shadowed_by`, the contract picks the one whose sorted-ID tuple is lex-smallest.
- **Trailing newline missing.** Every output must end with exactly one `\n`. Missing or doubled newlines fail strict JSON formatting checks.
- **Banker's rounding.** `coverage_percent` uses Python's default rounding mode (round-half-to-even). `2.345` rounds to `"2.34"`, not `"2.35"`.
