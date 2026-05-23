# Playbook Drift Semantics

## 1. Playbook Parsing & Play Naming
- Parse both playbooks (`baseline-playbook.yml` and `current-playbook.yml`) as lists of YAML plays.
- For each play, determine `play_name` using `play.name`. If it is a missing, empty, or whitespace-only string, use the exact fallback string `unnamed` (whitespace-stripped).

## 2. Task Identity
- Task identity is the two-tuple `(task_name, play_name)`.
- If `task.name` is a non-empty string, `task_name` is `task.name` (whitespace-stripped).
- If `task.name` is missing or empty, use the first key of the task mapping that is NOT one of the following special task-level keywords:
  `name`, `when`, `loop`, `register`, `vars`, `tags`, `become`, `become_user`, `notify`.
- If no such module/action key exists on the task, silently ignore the task.

## 3. Parameter Normalization
Extract a canonical parameter map from each task:
- Find the module key used (the key that determined `task_name` if `task.name` was missing).
- **Mapping Value**: If the module key value is a YAML mapping (dictionary), copy every child key and value verbatim into the canonical parameters.
- **Scalar Value**: If the module value is a non-null scalar (string, integer, boolean, list, etc.), place the value under the literal key `__module_value`.
- **Null Value**: If the module value is null or absent, do not populate `__module_value`.
- **Task Keywords**: Copy any task-level keys that are present from: `when`, `loop`, `register`, `vars`, `tags`, `become`, `become_user`, `notify` verbatim. Do not copy the module key itself into parameters.

## 4. Deduplication
- Within a single play, if multiple tasks produce the same `(task_name, play_name)` identity, retain only the **first** task in document order. Silently ignore later duplicates.

## 5. Drift Categorization
- **Added Tasks**: Task identity exists in current but not baseline. Output must include fields: `task_name`, `play_name`, `module` (the module key), and `parameters`.
- **Removed Tasks**: Task identity exists in baseline but not current. Output must include fields: `task_name`, `play_name`, `module`, and `parameters`.
- **Modified Tasks**: Task identity exists in both, but their parameter maps differ.
  - Output fields: `task_name`, `play_name`, and `changed_parameters`.
  - `changed_parameters` lists every differing key (`old_value != new_value`). Keys are sorted ASCII ascending. Each key maps to `{"old_value": ..., "new_value": ...}`.
  - If a task exists in both and has no differing parameters, it is omitted.
