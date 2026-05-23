# Tie-break notes

## Tie-break modes

`policy.tie_breaker` selects one of three modes. The mode determines:

- the sequence in which rules are walked when evaluating a flow,
- the relation "earlier than" used for shadow detection and escalation warnings,
- the rule IDs captured in `evaluated_rule_ids`.

### `priority_then_id`

Sort rules by `priority` descending; within ties, by `id` ASCII ascending. Highest priority rule fires first. Within priority `100`, rule `r03` fires before `r07`.

### `priority_lowest_wins`

Sort rules by `priority` ascending; within ties, by `id` ASCII ascending. Lowest priority rule fires first. This mode reverses the usual intuition — rule with `priority = 1` runs before rule with `priority = 1000`.

### `id_only`

Ignore priority entirely. Sort by `id` ASCII ascending. `r01` runs first regardless of priority.

## Equivalence-class iteration

The greedy elimination for `equivalence_classes` always iterates candidate IDs in ASCII ascending order, **independent** of `tie_breaker`. The `tie_breaker` is still used inside the elimination check (re-evaluating the candidate-removed rule set), but the outer iteration order is fixed.

## Worked example

For four rules `r01, r02, r03, r04` with priorities `200, 100, 100, 50`:

| Tie-break | Evaluation order |
|---|---|
| `priority_then_id` | `r01, r02, r03, r04` |
| `priority_lowest_wins` | `r04, r02, r03, r01` |
| `id_only` | `r01, r02, r03, r04` |

Note that for this set, `priority_then_id` and `id_only` produce the same order, but they will diverge whenever IDs and priorities are not co-monotonic.
