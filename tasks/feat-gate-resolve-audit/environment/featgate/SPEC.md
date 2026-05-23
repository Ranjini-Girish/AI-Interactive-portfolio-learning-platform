Normative contract for the feature-gate dependency resolve audit. Inputs are UTF-8 JSON with ASCII-only strings. Outputs use two-space indentation, recursively sorted keys, ASCII only, and one trailing newline per root object.

Read `policy.json` for string `root_package`, integer `default_epoch` (E0), and array `conflict_sets` where each element is a sorted pair of distinct feature names that cannot both be enabled. Read `manifest.json` for array `requested` of feature names to enable on the root package. Read `overrides.json` for array `patches`; each patch has string `package`, string `feature`, and exactly one of boolean `force_on` or boolean `force_off`.

Enumerate `packages/*.json`. Each package has string `name`, array `default_features`, object `features` mapping feature name to dependency feature paths (`other/feature`), and array `deps` of objects with string `name`, integer `epoch`, array `features` to enable on the dependency, and optional boolean `optional` default false. Optional dependencies activate only when `epoch >= default_epoch` and every listed feature resolves on the named package.

Propagation starts from `root_package` with `default_features` plus every `requested` feature that exists on that package. Queue unmet dependency paths `pkg/feat` (split on the first `/`). A feature is enabled on a package when it is default, requested (root only), pulled by an enabled feature's dependency list, or forced on by a matching patch. A patch with `force_off` disables that feature even if propagation would enable it; `force_on` enables it and still enqueues its dependencies.

After propagation, apply `conflict_sets`: for each pair, if both features are enabled anywhere in the graph, disable the lexicographically larger feature name globally (remove it and its exclusive dependents from the enabled set, but do not re-enable conflicting mates).

Package status is `active` when at least one feature is enabled on it, `dormant` when the package was reached but no feature remains enabled, and `blocked` when an optional dependency failed epoch or feature resolution. Unreachable packages are omitted.

Emit `package_states.json` with `packages` sorted by `name`. Each row has `enabled_features` (sorted strings), `name`, and `status` in `active`, `blocked`, or `dormant`.

Emit `conflict_report.json` with `drops` sorted by `feature` then `package`. Each row names a `feature`, its `package`, and string `reason` in `conflict`, `forced_off`, or `optional_blocked`.

Emit `summary.json` with integers `active_total`, `blocked_total`, `conflict_drop_total`, `dormant_total`, `forced_off_total`, `optional_blocked_total`, `package_total`, and string `root_package`.

`FGR_DATA_DIR` defaults to `/app/featgate`, `FGR_AUDIT_DIR` to `/app/audit`. Never modify inputs.
