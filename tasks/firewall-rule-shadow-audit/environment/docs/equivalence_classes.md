# Equivalence classes

The minimal equivalent rule set is the smallest subset of the input rules that produces, for every flow, the same `(verdict, matched_rule_id)` pair as the full rule set. The pair-equality requirement is **stricter** than the security-posture equality used for the `redundant` status.

## Invariance

For every flow `F`, the original `(verdict, matched_rule_id)` is computed using the full rule set. After any candidate removal, every flow must still produce the same pair — including `matched_rule_id`. A flow that originally matched `r03` and now matches `r08` violates invariance even if both rules emit the same verdict.

## Greedy fixpoint

1. Sort all current rule IDs ASCII ascending.
2. Walk the sorted list. For each candidate, build a rule set with the candidate removed and re-evaluate every flow.
3. If every flow's `(verdict, matched_rule_id)` pair matches the original, commit the removal and append the candidate ID to `removed_rule_ids`. Restart from the smallest remaining ID.
4. If a full walk yields no successful removal, terminate.

Output:

- `minimal_rule_ids`: the surviving rule IDs, sorted ASCII ascending.
- `removed_rule_ids`: the eliminated rule IDs, sorted ASCII ascending.
- `verdict_invariant`: the literal boolean `true`.

## Why ASCII-then-restart matters

Different walking strategies (priority order, no-restart, batch removal) produce different minimal sets. The contract pins one canonical path: ASCII-ascending iteration with restart-on-success. Any other strategy may yield an incorrect `removed_rule_ids`.
