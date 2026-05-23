# Output format

All four output files share the same JSON conventions:

- UTF-8 encoding.
- Two-space indent at every depth.
- `ensure_ascii=True` (Python default for `json.dumps`) — no raw non-ASCII bytes.
- `sort_keys=True` — keys lexicographically sorted at every depth.
- A single trailing newline (`\n`) after the closing brace.

A canonical write looks like:

```python
text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
path.write_text(text, encoding="utf-8")
```

## Per-file contents

### `flow_verdicts.json`

Top level: object with single key `flows` whose value is a list of verdict objects sorted by `id` ASCII ascending. Each verdict has keys: `evaluated_rule_ids`, `id`, `matched_rule_id`, `verdict`. `matched_rule_id` is the literal `null` (not `"null"`) when no rule matched. `verdict` is one of `"allow"`, `"deny"`, `"default"`.

### `rule_analysis.json`

Top level: object with single key `rules` whose value is a list of analysis objects sorted by `id` ASCII ascending. Each analysis has keys: `coverage_percent`, `id`, `matched_flows`, `shadowed_by`, `status`. `coverage_percent` is a string like `"4.35"` or `"100.00"` — always two fractional digits.

### `policy_summary.json`

Top-level keys: `default_action_uses`, `effective`, `escalation_warnings`, `redundant`, `shadowed`, `total_rules`, `unreachable`. Counts are non-negative integers. `escalation_warnings` is a list, possibly empty, of `{earlier_rule_id, rule_id, type}` objects sorted by `(rule_id, earlier_rule_id)` ASCII ascending.

### `equivalence_classes.json`

Top-level keys: `minimal_rule_ids`, `removed_rule_ids`, `verdict_invariant`. The first two are lists of strings sorted ASCII ascending. `verdict_invariant` is the literal boolean `true`.
