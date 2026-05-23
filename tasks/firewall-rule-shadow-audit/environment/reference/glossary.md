# Glossary

- **Action** — what the firewall does on match: `"allow"` or `"deny"`.
- **CIDR** — IPv4 network in `address/prefix` form (e.g. `10.0.20.0/24`). Host bits in the address are ignored after normalization.
- **Coverage** — fraction of the test flow universe a rule's predicate matches, expressed as a percentage with two fractional digits.
- **Default action** — the verdict applied when no rule matches; comes from `policy.default_action`.
- **Direction** — either `"ingress"` (into the network) or `"egress"` (out of the network).
- **Effective** — a rule whose removal would change at least one flow's allow/deny outcome.
- **Equivalence class** — the smallest rule subset that produces, per flow, the same `(verdict, matched_rule_id)` pair as the full set.
- **Escalation warning** — `(allow, deny)` pair where the allow appears earlier in evaluation order and the deny would otherwise fire.
- **Evaluation order** — the deterministic order in which rules are walked; depends on `policy.tie_breaker`.
- **First-match-wins** — the firewall verdict for a flow is determined by the first rule that matches; later rules are not consulted for that flow.
- **Matched flows** — the flows whose match predicate a rule satisfies, computed without considering priority or other rules.
- **Predicate** — the conjunction of direction, source CIDR, destination CIDR, protocol, and port ranges that a rule tests.
- **Redundant** — a non-shadowed rule whose removal leaves every flow's allow/deny outcome unchanged after substituting `policy.default_action` for `"default"`.
- **Shadowed** — a rule whose `matched_flows` is non-empty but covered by the union of higher-priority rules' `matched_flows`.
- **Shadowed-by cover** — the lex-smallest minimum-cardinality subset of higher-priority rules whose union covers a shadowed rule's matched flows.
- **Tie-breaker** — sort key resolution among same-priority rules; controlled by `policy.tie_breaker`.
- **Unreachable** — a rule whose predicate matches no flow in the test set.
- **Verdict** — `"allow"`, `"deny"`, or `"default"` (the latter only when no rule matched).
