# Quality Findings Specification

Quality findings flag crates (or the graph as a whole) that exhibit
undesirable characteristics. Each finding has a `type`, `severity`,
`module` (the crate name, or `null` for graph-level findings), and
optionally `details`.

## Finding Types

| Type                 | Severity   | Trigger (strictly greater / less)                  |
|----------------------|------------|----------------------------------------------------|
| `dependency_cycle`   | `critical` | An SCC with more than 1 member exists.             |
| `feature_conflict`   | `critical` | Both features of a conflict pair are active.        |
| `workspace_feature_exclusion` | `critical` | Features from the same exclusion group are active across different crates. |
| `deep_module`        | `high`     | depth **>** `thresholds.max_depth`                 |
| `excessive_fan_in`   | `medium`   | fan_in **>** `thresholds.max_fan_in`               |
| `excessive_fan_out`  | `medium`   | fan_out **>** `thresholds.max_fan_out`             |
| `oversized_crate`    | `medium`   | active_size **>** `thresholds.oversized_crate_bytes` |
| `high_instability`   | `low`      | instability **>** `thresholds.max_instability`     |
| `unstable_deep_module` | `high`   | depth **>** `max_depth` **AND** instability **>** `max_instability` |
| `dead_feature`       | `low`      | A feature is declared but never activated.          |
| `unreachable_module` | `info`     | Crate is not reachable from the workspace root.    |

**Important**: all numeric thresholds use **strictly greater than**
(`>`). A value exactly equal to the threshold does **not** trigger the
finding.

## Finding Details

### `dependency_cycle`
- `module`: `null` (graph-level).
- `details`: `{"members": ["crate_a", "crate_b", ...]}` — the sorted
  member list of the SCC.
- Emit one finding per cycle (per SCC with size > 1).

### `feature_conflict`
- `module`: the crate name where the conflict was detected.
- `details`: `{"features": ["feat_a", "feat_b"]}` — the conflicting pair,
  sorted alphabetically.

### `workspace_feature_exclusion`
- `module`: `null` (workspace-level).
- `details`: `{"group": "<group_name>", "violations": [{"crate": "...", "feature": "..."},...]}`
  where violations is the list of (crate, feature) pairs that activated a
  feature from this exclusion group, sorted by (crate ASC, feature ASC).
- The `feature_exclusion_groups` map is in `config.json`. Each key names
  a group and maps to a list of feature names. For each group, scan all
  **reachable** crates' resolved (active) features. If two or more
  distinct crates each have at least one feature from the group active,
  emit one finding per group with the full list of violating crate+feature
  pairs.
- If only one crate has a group feature active, no finding is emitted.

### `deep_module`
- `module`: crate name.
- `details`: `{"depth": <int>, "threshold": <int>}`.

### `excessive_fan_in`
- `module`: crate name.
- `details`: `{"fan_in": <int>, "threshold": <int>}`.

### `excessive_fan_out`
- `module`: crate name.
- `details`: `{"fan_out": <int>, "threshold": <int>}`.

### `oversized_crate`
- `module`: crate name.
- `details`: `{"active_size": <float>, "threshold": <int>}`.

### `high_instability`
- `module`: crate name.
- `details`: `{"instability": <float>, "threshold": <float>}`.

### `unstable_deep_module`
- `module`: crate name.
- `details`: `{"depth": <int>, "instability": <float>,
  "depth_threshold": <int>, "instability_threshold": <float>}`.
- This is a **compound** finding. Emit it when a crate triggers **both**
  `deep_module` and `high_instability` conditions simultaneously. When a
  crate qualifies for `unstable_deep_module`, **still** emit separate
  `deep_module` and `high_instability` findings — the compound finding is
  additional, not a replacement.

### `dead_feature`
- `module`: crate name.
- `details`: `{"feature": "<feature_name>"}`.
- For each **reachable** crate, compare the set of features declared in
  its `features` map against the resolved (active) feature set. Any
  feature declared but not activated is "dead." Emit one finding per dead
  feature. **Exclude** unreachable crates entirely.

### `unreachable_module`
- `module`: crate name.
- `details`: `{}`.

## Sort Order

Findings are sorted by a composite key:

1. **severity_rank descending** (critical=4 first, info=0 last).
2. **finding type ascending** (alphabetical).
3. **module ascending** (`null` sorts before any string — use empty
   string `""` for comparison purposes).

## Severity Summary

Include a `by_severity` map counting findings at each severity level.
Include only severity levels that have at least one finding.
