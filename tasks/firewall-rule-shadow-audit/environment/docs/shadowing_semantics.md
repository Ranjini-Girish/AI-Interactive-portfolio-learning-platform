# Shadowing semantics

A rule is `shadowed` when its `matched_flows` set is non-empty and entirely covered by the union of higher-priority rules' `matched_flows` sets. The interesting case is **composite shadowing**: a rule whose flows are covered by the *union* of multiple higher-priority rules even though no single higher-priority rule covers them.

## `shadowed_by` minimum cover

For every shadowed rule, `shadowed_by` is the **lex-smallest minimum-cardinality** subset of earlier rule IDs whose `matched_flows` union covers the shadowed rule's `matched_flows`.

Procedure:

1. Let `target = matched_flows(R)`.
2. Let `candidates = matched_flows(rule)` for every rule `rule` that comes strictly before `R` in evaluation order.
3. Search for the smallest `k` such that some size-`k` subset of `candidates`' rule IDs has its union of matched-flows ⊇ `target`.
4. Among all size-`k` covers, return the one whose tuple of IDs (sorted ASCII ascending) is lex-smallest.

The output `shadowed_by` is itself sorted ASCII ascending.

## Examples

- Single-rule shadow: if rule `R` has `matched_flows = {f02, f08}` and an earlier rule covers exactly those flows, `shadowed_by = [<that_rule_id>]`.
- Composite shadow: if `R.matched_flows = {f08, f09}` and rule `r01` covers `{f01, f09, f13, f14}` while `r02` covers `{f02, f08}`, neither alone covers `R` but `r01 ∪ r02` does. `shadowed_by = ["r01", "r02"]`.
- Lex tiebreak: if `R.matched_flows = {f01, f02, f03, f04}` and there are two size-2 covers `{r03, r04}` and `{r05, r06}`, both with union ⊇ `R`, then `shadowed_by = ["r03", "r04"]` because `("r03", "r04") < ("r05", "r06")` in tuple ASCII order.

## Non-applicability

- Unreachable rules: `shadowed_by = []` — there is nothing to cover.
- Redundant or effective rules: `shadowed_by = []` — by definition not shadowed.
