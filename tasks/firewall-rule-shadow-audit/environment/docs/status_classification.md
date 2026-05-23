# Status classification

Every rule is assigned exactly one of four status labels. Labels are tested in priority order and the first applicable label wins.

## 1. `unreachable`

`R.matched_flows` is empty. `R` cannot match any flow in the test set. `shadowed_by` is `[]`. Examples include:

- A rule whose source or destination CIDR is malformed.
- A rule whose port lists are empty or have no satisfiable ranges.
- A rule whose direction or CIDR or protocol simply does not intersect any flow.

## 2. `shadowed`

`R.matched_flows` is non-empty AND is a subset of the union of `matched_flows` for all rules that come strictly before `R` in evaluation order. `R` can never fire because every flow it could match is taken first by an earlier rule (regardless of action).

`shadowed_by` is the lex-smallest minimum-cardinality subset of those earlier rule IDs whose `matched_flows` union covers `R.matched_flows`. See `shadowing_semantics.md`.

## 3. `redundant`

`R` is not unreachable and not shadowed, but removing `R` from the rule set leaves every flow's **security verdict** unchanged. Security verdict is the rule's action when matched, or `policy.default_action` when the flow's `verdict` is `"default"` after removal. Matched-rule identity may change; only the allow/deny outcome must be preserved.

A common redundancy pattern: a deny rule with no later contradictor when `policy.default_action == "deny"` is redundant — its flows would default-deny anyway.

`shadowed_by` is `[]`.

## 4. `effective`

None of the above. Removing `R` would change at least one flow's allow/deny outcome. `shadowed_by` is `[]`.

## Mutual redundancy

Two rules can each individually be redundant when the other is present. For example, an explicit allow plus a broader allow at lower priority — removing either leaves the other to catch the same flows. Both will be marked `redundant`. The downstream `equivalence_classes` minimizer picks one to drop based on its own (stricter) invariant.
