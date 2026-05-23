# Overview

The audit ingests three input files under `/app/data/` and produces four output files under `/app/output/`:

- Inputs: `rules.json`, `flows.json`, `policy.json`.
- Outputs: `flow_verdicts.json`, `rule_analysis.json`, `policy_summary.json`, `equivalence_classes.json`.

Every output is deterministic given the inputs. There is no I/O, no randomness, no clock dependency, no network access. JSON is emitted in canonical form (UTF-8, two-space indent, ASCII-only, sorted keys at every depth, trailing newline).

The audit answers four questions about a stateless firewall:

1. What does this rule set decide for each test flow?
2. Which rules are dead, dominated, or redundant?
3. What does the headline summary look like?
4. What is the smallest equivalent rule set that produces the same outputs?

Subsequent documents cover: matching semantics, status classification, the lex-smallest minimum cover for `shadowed_by`, escalation warnings, equivalence-class minimization, output formatting rules, edge cases, and sorting conventions.
