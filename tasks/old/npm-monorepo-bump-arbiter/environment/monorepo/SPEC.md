# NPM Monorepo Bump Arbiter — Output Contract

This file is part of the read-only input dataset under `/app/monorepo/`. It defines exactly how the five output JSON files at `/app/arbitration/` must be derived from the inputs. Every requirement is binding.

## Inputs

- `monorepo_manifest.json` — `{packages: [name], severity_block_threshold: "low"|"medium"|"high"|"critical", allow_yanked_pinned: bool}`.
- `governance/policy.json` — `{engines_node_workspace: ">=A.B.C <D.E.F", peer_intersection_required: bool}`. Always treat `peer_intersection_required` as `true`.
- `packages/<name>.json` — `{name, version, engines_node, dependencies: {dep: {range, scope, exports_used}}, dev_dependencies: {dep: {range, scope, exports_used}}}`. Every entry's `scope` is one of `"prod"`, `"dev"`, `"peer"`. `exports_used` is a list of subpath-condition strings (e.g. `"import"`, `"require"`, `"types"`, `"node"`); an empty list means no exports constraint.
- `registry/<dep>.json` — `{name, dist_tags: {tag: version}, versions: [{version, engines_node, exports_conditions, peer_constraints: {peer: range}, advisory_ids: [string], yanked: bool}]}`. `dist_tags` always contains `"latest"`; may also contain `"next"`, `"canary"`.
- `advisories.json` — `{advisories: [{advisory_id, dep, vulnerable_range, patched_range, severity, day_published}]}`.
- `current_lock.json` — `{locks: {dep: version}}`.
- `incident_log.json` — `{events: [{event_id, day, kind, accepted, ...}]}`.
- `pool_state.json` — `{current_day}`.

## Range syntax (exactly four forms; reject anything else)

- `"^X.Y.Z"` — caret. Covers `[X.Y.Z, X+1.0.0)` when `X >= 1`, `[0.Y.Z, 0.Y+1.0)` when `X == 0 AND Y > 0`, `[0.0.Z, 0.0.Z+1)` when `X == 0 AND Y == 0`.
- `"~X.Y.Z"` — tilde. Covers `[X.Y.Z, X.Y+1.0)`.
- `">=A.B.C <D.E.F"` — half-open interval, with a single space between the two comparators.
- `"X.Y.Z"` — exact-version singleton `{X.Y.Z}`. No `=` prefix is ever used.

Workspace-protocol prefixes (`workspace:*`, `workspace:^`, `workspace:~`) are a separate form handled by the workspace-protocol rule below; they never enter the four-form range parser. Version comparison is tuple comparison on `(major, minor, patch)`.

## Range intersection (for peer intersection only)

The intersection of two ranges is the half-open interval `[max(lower_A, lower_B), min(upper_A, upper_B))`. The interval is **empty** iff `max_lower >= min_upper`. Single-version forms `"X.Y.Z"` are treated as `[X.Y.Z, X.Y.Z+1)` for intersection. The serialised intersection is `">=L.L.L <U.U.U"`; when the intersection is empty, it is JSON `null`.

## Incident-log filtering

An event is **accepted** iff `accepted == true` AND `day <= pool_state.current_day` AND `kind` is one of `"force_freeze"`, `"dist_tag_pin"`, `"advisory_override"`. Every other event is silently ignored and counted in `summary.ignored_incident_events`. Event scopes:

- `force_freeze` — field `dep`; locks that dep across every consuming entry.
- `dist_tag_pin` — fields `dep`, `dist_tag`; overrides every consuming entry for that dep to `registry[dep].dist_tags[dist_tag]`.
- `advisory_override` — field `advisory_id`; cancels that one advisory.

When two accepted events of the **same kind and same scope** exist, keep only the one with the largest `day`; break ties by ASCII-smallest `event_id`. Events dropped by this deduplication step have already passed the accept-filter and therefore are NOT added to `summary.ignored_incident_events`.

## Per-entry eligibility (registry resolutions only)

For every per-entry `(package, dep)` declaration whose `range` is NOT a workspace-protocol form, a registry version `v` is **eligible** iff all of:

1. `v.version` lies in the entry's declared `range`.
2. `engines_node(v)` is a **superset** of `governance.engines_node_workspace`, i.e. `v.engines_node.lower <= workspace_engines.lower` AND `v.engines_node.upper >= workspace_engines.upper`.
3. `v.yanked == false`, OR (`monorepo_manifest.allow_yanked_pinned == true` AND `current_lock.locks[dep] == v.version`).
4. For every active advisory `A` on `dep` (`A.severity >= severity_block_threshold` AND no accepted `advisory_override` for `A.advisory_id`), `v.version` is not in `A.vulnerable_range`. Severity rank: `low=0, medium=1, high=2, critical=3`.

The **requested exports** for an entry are the list `exports_used` declared by the consuming package. A version `v` **supports** condition `c` iff `c` is in `v.exports_conditions`.

## Selection algorithm

Per entry, the **chosen version** is selected as follows:

1. **Workspace-protocol form.** If `range` starts with `"workspace:"`:
   - `resolution_kind = "workspace_protocol"`. `protocol_variant` is `"star"`, `"caret"`, or `"tilde"` after the colon.
   - If `dep` is a workspace package (`dep` appears in `monorepo_manifest.packages`), `chosen_version = packages[dep].version`. `action` is `"hold"` when `current_lock.locks[dep] == chosen_version`, `"bump"` when `chosen_version > current`, `"downgrade"` when `chosen_version < current`. `reason = "satisfied"`. `source = "planner"`. Exports cascade does NOT apply (the workspace package controls its own exports).
   - Otherwise (`dep` is external), `action = "block_no_workspace_target"`, `chosen_version = null`, `reason = "no_workspace_target"`, `source = "planner"`, `exports_dropped_set = []`.
2. **`force_freeze` directive** on this `dep` (highest registry-side priority). `resolution_kind = "registry"`. `chosen_version = current_lock.locks[dep]`. If that version fails eligibility check 4 (active advisory), `action = "freeze_unsafe"`, every blocking advisory's status becomes `"still_open_frozen"`, `reason = "freeze_advisory_conflict"`. Otherwise `action = "freeze"`, `reason = "satisfied"`. Yanked-but-pinned is permitted under `allow_yanked_pinned`; if even pinning would not allow it (failed check 3 with `allow_yanked_pinned == false`), `action = "freeze_unsafe"` regardless of advisory state and `reason = "freeze_advisory_conflict"`. `source = "incident_log_force_freeze"`. Exports cascade does not apply.
3. **`dist_tag_pin` directive** on this `dep` (only when no `force_freeze` for `dep`). `resolution_kind = "registry"`. `chosen_version = registry[dep].dist_tags[dist_tag]`. If that version fails any eligibility check, `action = "block_dist_tag_unsafe"`, `chosen_version = null`, `reason = "dist_tag_unsafe"`, every blocking advisory's status becomes `"unmitigated_pinned"`. Otherwise `action = "dist_tag_pin"`, `reason = "satisfied"`. `source = "incident_log_dist_tag_pin"`. Exports cascade does not apply.
4. **Planner selection.** `resolution_kind = "registry"`. Compute the eligible set. From it, pick the **highest** version `v_max`. If `v_max` supports every condition in `exports_used`, `chosen_version = v_max` and `exports_dropped_set = []`. Otherwise apply the **exports-downgrade rule**: first walk the eligible set in descending version order and stop at the first version supporting every condition in `exports_used`; if such a version exists, `chosen_version = that version` and `exports_dropped_set = []`. If no eligible version supports the full `exports_used`, identify the **drop pool** as the conditions in `exports_used` that `v_max` does not support, sorted in ASCII order. Drop them one at a time in that order; after each drop, find the highest eligible version supporting every condition that remains; stop at the first drop that yields a satisfying version. The final `chosen_version` is the highest such eligible version; `exports_dropped_set` is the sorted list of conditions actually dropped. Action is `"hold"`, `"bump"`, or `"downgrade"` by comparing `chosen_version` to `current_lock.locks[dep]` (treat missing-from-lock as `chosen_version` itself for the comparison). `reason = "exports_downgrade"` when `exports_dropped_set` is non-empty, else `"satisfied"`. `source = "planner"`. If the eligible set is empty, `action = "block_no_eligible_version"`, `chosen_version = null`, `reason = "no_eligible_version"`, `exports_dropped_set = []`.

## Peer satisfaction (post-selection)

After every entry's `chosen_version` is decided, build the **peer link graph**: for every entry with a non-null `chosen_version` on a registry dep, every `(peer_name, range)` pair in `v.peer_constraints` adds one consumer link. The link's `dep_chain` is the string `"<package>::<dep>"` (consumer package and the dep declaring the peer requirement).

For each `peer_name` that appears in at least one link, compute the **intersection** of every contributing `range` per the range-intersection rule above. The **resolved peer version** is:

- The chosen version of the peer dep when that dep is itself an entry in `bump_decisions` with a non-null chosen value (whether resolved via workspace-protocol or registry; pick the highest such chosen version across all entries naming the peer).
- Otherwise `null`.

`peer_status` is:

- `"unsatisfiable_intersection"` when the intersection is empty.
- `"peer_unresolved"` when the intersection is non-empty AND `resolved_peer_version` is `null`.
- `"outside_intersection"` when both are present but `resolved_peer_version` is not in the intersection.
- `"satisfied"` otherwise.

## Engines compatibility

Per workspace package, compare the package's own `engines_node` range against `governance.engines_node_workspace`. The package must declare a **subrange** (its `lower >= workspace.lower` AND `upper <= workspace.upper`). `package_engines_status` is `"subrange"` when both hold, `"lower_violated"` when only the lower fails, `"upper_violated"` when only the upper fails, `"both_violated"` when both fail. `lower_exceeded_by` is `"X.Y.Z"` componentwise of `workspace.lower - package.lower` (negative components clamped to `"0.0.0"`) when `lower_violated` or `both_violated`, else `"0.0.0"`. `upper_exceeded_by` is `"X.Y.Z"` componentwise of `package.upper - workspace.upper` (negative components clamped to `"0.0.0"`) when `upper_violated` or `both_violated`, else `"0.0.0"`. `engines_blocked_versions_count` is the count of distinct `(dep, version)` pairs across the package's `dependencies` AND `dev_dependencies` (non-workspace entries only) that fail eligibility check 2 alone — i.e. the version lies in the entry's range, is not yanked-or-pinned, faces no severity-blocking advisory, but its `engines_node` is not a superset of `governance.engines_node_workspace`.

## Advisory status

For every advisory `A`:

- `"overridden"` when an accepted `advisory_override` event has `advisory_id == A.advisory_id`.
- `"inactive_low_severity"` when `A.severity < severity_block_threshold` AND not overridden.
- `"still_open_frozen"` when active and at least one entry chose `freeze_unsafe` against `A` (set by rule 2 above).
- `"unmitigated_pinned"` when active and at least one entry chose `block_dist_tag_unsafe` against `A` (set by rule 3 above) AND no entry on `A.dep` is `still_open_frozen`.
- `"mitigated_by_exports_drop"` when active, none of the above, and at least one consuming entry's `exports_dropped_set` is non-empty AND that entry's `chosen_version` is outside `A.vulnerable_range` AND that entry's chosen version is inside `A.patched_range`.
- `"resolved_by_bump"` when active, none of the above, and every consuming entry on `A.dep` has its `chosen_version` outside `A.vulnerable_range` AND that chosen version is inside `A.patched_range`.
- `"still_open"` otherwise.

`mitigation_method` is derived from `status` by this exact lookup:

- `"resolved_by_bump"` → `"bump"`
- `"mitigated_by_exports_drop"` → `"exports_drop"`
- `"still_open_frozen"` → `"frozen"`
- `"unmitigated_pinned"` → `"pinned"`
- `"overridden"` → `"override"`
- `"inactive_low_severity"` → `null`
- `"still_open"` → `null`

`patched_versions` is the sorted list of distinct `chosen_version` values among consuming entries for `A.dep` that lie inside `A.patched_range`, excluding `null`.

## Output schemas

All five outputs are written under `/app/arbitration/`. Canonical encoding: UTF-8 JSON with two-space indentation, object keys emitted in sorted order at every nesting level, and a single trailing newline after the closing brace.

- `bump_decisions.json` = `{"entries": [{package, dep, resolution_kind, protocol_variant, current_version, chosen_version, action, reason, exports_dropped_set, scope, source}]}`. Sorted by `(package, dep)`. `protocol_variant` is `null` when `resolution_kind == "registry"`. `current_version` is `null` when the dep is missing from `current_lock`. `exports_dropped_set` is alphabetically sorted.
- `peer_satisfaction_report.json` = `{"peer_links": [{peer_name, consumers: [{package, dep_chain, declared_range}], intersection_range, resolved_peer_version, peer_status}]}`. Sorted by `peer_name`. `consumers` is sorted by `(package, dep_chain)`.
- `engines_compatibility.json` = `{"engines_node_workspace_lower, engines_node_workspace_upper, packages: [{package, package_engines_lower, package_engines_upper, package_engines_status, lower_exceeded_by, upper_exceeded_by, engines_blocked_versions_count}]}`. Sorted by `package`.
- `advisory_status.json` = `{"advisories": [{advisory_id, dep, severity, status, mitigation_method, patched_versions, day_published}]}`. Sorted by `advisory_id`.
- `summary.json` = `{engines_node_workspace_lower, engines_node_workspace_upper, total_packages, total_external_deps, total_entries, action_counts, resolution_kind_counts, peer_status_counts, advisory_counts, engines_blocked_versions_total, ignored_incident_events, lockfile_drift_count}`. `action_counts`, `resolution_kind_counts`, `peer_status_counts`, and `advisory_counts` contain only the enum values actually observed, keys emitted in sorted order. `engines_blocked_versions_total` is the sum of every package's `engines_blocked_versions_count`. `lockfile_drift_count` is the count of distinct deps for which at least one entry's `chosen_version` differs from `current_lock.locks[dep]` (treat missing-from-lock as a drift when `chosen_version != null`).
