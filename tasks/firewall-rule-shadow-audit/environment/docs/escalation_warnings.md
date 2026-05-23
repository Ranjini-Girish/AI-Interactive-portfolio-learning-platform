# Escalation warnings

Escalation warnings flag deny rules whose intent may be defeated by an earlier allow. The output is a list under `policy_summary.escalation_warnings`.

## Emission rule

For every rule `D` such that:

- `D.action == "deny"`,
- `D.status` is not `"unreachable"` and not `"redundant"` (a `"shadowed"` deny **is** included),
- `D.matched_flows` is non-empty,

and for every rule `A` such that:

- `A.action == "allow"`,
- `A` is strictly before `D` in evaluation order,
- `A.matched_flows ∩ D.matched_flows ≠ ∅`,

emit:

```
{ "earlier_rule_id": A.id, "rule_id": D.id, "type": "deny_after_allow" }
```

## Why redundant denies are excluded

A redundant deny does not change any flow's outcome. Flagging it as a "risk" would surface false positives every time the policy default already denies. Only deny rules that would otherwise fire are surfaced here.

## Sorting

The list is sorted by `(rule_id, earlier_rule_id)` ASCII ascending. Multiple earlier allows can pair with the same deny; each is its own entry.
