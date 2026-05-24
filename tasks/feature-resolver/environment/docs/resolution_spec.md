# Feature Resolution Specification

## Overview

Feature resolution determines which features are active on each crate and
which optional dependencies become real dependencies. Resolution starts
from the workspace root crate and propagates through the dependency graph.

## Definitions

- **Feature**: a named flag that controls conditional compilation. Defined
  in a crate's `features` map where the key is the feature name and the
  value is a list of other features or dependency activations it enables.
- **`dep:X` syntax**: a feature entry like `"dep:X"` in a feature's
  enable-list means "activate the optional dependency named X". The
  optional dependency must exist in the crate's `dependencies` with
  `optional: true`.
- **Default features**: the features listed under the `"default"` key.
  They are enabled when a dependent includes this crate with
  `default_features: true`.

## Resolution Algorithm

### Step 1: Collect Feature Requests

For each crate reachable from the root, collect all feature requests
from every dependent that depends on it:

1. If `default_features` is `true` for that dependency edge, add the
   string `"default"` to the requested features.
2. Add all explicitly listed `features` from the dependency edge.
3. Take the **union** of all requested feature sets across all
   dependency edges pointing to this crate.

**Default-feature unification rule**: if **any** dependent requests
`default_features: true`, the crate's default features are enabled —
even if another dependent requests `default_features: false`.

### Step 2: Expand Feature Chains

Starting from the collected feature set, repeatedly expand features
by following the enable-lists in the crate's `features` map:

1. For each active feature F, look up `features[F]` to get its
   enable-list.
2. For each entry in the enable-list:
   - If it starts with `"dep:"`, extract the dependency name and mark
     that optional dependency as activated. **Do not** add `"dep:X"` to
     the active feature set — it is a dependency activation, not a
     feature name.
   - Otherwise, it names another feature. Add that feature to the
     active set and expand it recursively.
3. The `"default"` pseudo-feature is expanded like any other: its
   enable-list is `features["default"]`.
4. Continue until no new features are added (fixed-point).

### Step 3: Activate Optional Dependencies

After feature expansion, examine the crate's `dependencies`:

- Any dependency with `optional: true` whose name appears in a
  `"dep:X"` activation from Step 2 becomes a **real** (resolved)
  dependency.
- Dependencies with `optional: false` are always real dependencies.
- Optional dependencies that were **not** activated by any feature
  are excluded from the resolved dependency graph.

### Step 4: Propagate to Dependencies

For each resolved dependency of a crate, look up the dependency
specification (`default_features`, `features`) and feed it into
Step 1 for the target crate. Process the entire graph breadth-first
or depth-first — the result is the same because of the union/fixed-point
semantics.

## Root Crate

The root crate (named in `workspace.json`) has its `"default"` features
enabled. No other features are requested for the root unless explicitly
stated in the workspace config.

## Unreachable Crates

Crates that are never reached during resolution (not transitively
depended on by the root) are **unreachable**. They appear in the output
with `reachable: false` and `resolved_features: null`. Their dependencies
are not resolved.

## Feature Conflicts

After resolution, check each crate's `feature_conflicts` list. Each
entry is a pair `[A, B]` of feature names. If both A and B are in the
crate's active feature set, emit a `feature_conflict` quality finding.

## Weak Features

After the main feature resolution (Steps 1–4) has converged for all
crates, perform a **weak-feature activation pass**:

Each crate may have a `weak_features` map. Each entry maps a feature
name to a list of conditions. A condition is a string `"crate/feature"`
meaning "the crate named `crate` is a resolved dependency of this crate
AND has `feature` in its resolved (active) feature set."

For each weak-feature entry, if **all** conditions in its list are
satisfied, add that feature to the crate's active feature set. Then
re-expand feature chains (Step 2) and re-activate optional deps
(Step 3) for that crate.

Weak features that activate may add new size weights and conditional
exports, but they do **not** create new dependency edges or propagate
to other crates. A weak feature is purely local to its crate.

**Important**: weak features that are activated do appear in
`resolved_features` but do **not** appear in `activated_optional_deps`
(since they are not optional dependency activations).

If a weak feature's name already exists in the crate's `features` map,
expand its chain. If it does not exist in `features`, treat it as a
leaf feature with no enable-list.

Run the weak-feature pass only **once** after the main resolution has
fully converged. Do not iterate weak features to a fixed point.

## Resolved Dependency Graph

The resolved graph contains one directed edge `(A, B)` for each crate A
that has B as a resolved dependency. Duplicate edges are collapsed.
Only resolved (activated) dependencies produce edges.
