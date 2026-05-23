# Sorting Rules

To ensure 100% deterministic output matching, the following strict sorting rules must be followed across all output files:

## 1. playbook_drift.json
- `added_tasks`: Sorted ASCII ascending by play/task identity: first by `task_name`, then by `play_name`.
- `removed_tasks`: Sorted ASCII ascending by play/task identity: first by `task_name`, then by `play_name`.
- `modified_tasks`: Sorted ASCII ascending by play/task identity: first by `task_name`, then by `play_name`.
- `changed_parameters` (inside modified tasks entries): Sorted ASCII ascending by parameter key.

## 2. dependency_impact.json
- `resolver_summary.missing`: Sorted ASCII ascending.
- `resolver_summary.conflicts`: Sorted ASCII ascending.
- `seed_modules`: Sorted ASCII ascending first by `task_ref`, then by `module`.
- `impacted_modules`: Sorted ASCII ascending by `name`.
- `triggered_by` (inside impacted modules): Sorted ASCII ascending.
- `cycles`: Each cycle group member list is sorted ASCII ascending. The outer list of cycle groups is sorted ASCII ascending by their first (minimum) member.
- `build_order`: Each group member list is sorted ASCII ascending. The sequence of groups must follow the canonical topological order tied by lexicographically smallest minimum member name.

## 3. remediation_plan.json
- `modules` (inside each step): Preserves the order from `build_order` (which is ASCII-sorted internally).
- `triggered_by` (inside each step): Sorted ASCII ascending.
