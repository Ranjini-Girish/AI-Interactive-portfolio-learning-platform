# Sorting rules

Every list and key set in the outputs has a deterministic order. The conventions are:

| Field | Sort |
|---|---|
| `flow_verdicts.flows` | by `id`, ASCII ascending |
| `flow_verdicts.flows[].evaluated_rule_ids` | evaluation order (NOT sorted) |
| `rule_analysis.rules` | by `id`, ASCII ascending |
| `rule_analysis.rules[].matched_flows` | ASCII ascending |
| `rule_analysis.rules[].shadowed_by` | ASCII ascending |
| `policy_summary.escalation_warnings` | by `(rule_id, earlier_rule_id)` ASCII ascending |
| `equivalence_classes.minimal_rule_ids` | ASCII ascending |
| `equivalence_classes.removed_rule_ids` | ASCII ascending |
| All JSON object keys at every depth | sorted by `json.dumps(..., sort_keys=True)` |

`evaluated_rule_ids` is the **only** list that is not sorted — it preserves the exact evaluation walk so a reader can trace the verdict.

## Tie-break inside evaluation order

Evaluation order itself depends on `policy.tie_breaker`:

- `priority_then_id`: priority descending, ties broken by id ASCII ascending.
- `priority_lowest_wins`: priority ascending, ties broken by id ASCII ascending.
- `id_only`: id ASCII ascending; priority is ignored.

The chosen evaluation order feeds:

- the verdict walk in `flow_verdicts`,
- the "earlier than" relation used in shadow detection and escalation warnings,
- the `evaluated_rule_ids` capture.

`equivalence_classes` greedy iteration uses ASCII ascending order regardless of `tie_breaker`.
