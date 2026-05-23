# Zone ingress matrix audit

This document is normative. All JSON emitted by the auditor must use UTF-8, two-space indentation, `sort_keys=True` at every object level, a single trailing newline after the closing brace or bracket of the root value, and no byte-order mark.

## Inputs

Read `/app/zoning/pool_state.json` for `current_day` (integer) and `audit_version` (string). Read `/app/zoning/policy/tier_weights.json` for mapping `weights` from tier name to positive integer weight. Read `/app/zoning/policy/implicit_matrix.json` for object `pairs` whose keys are strings `SRC_TIER->DST_TIER` where each tier is one of `internal`, `production`, or `staging`, and whose values are either `allow` or `deny`.

Enumerate every file `*.json` directly under `/app/zoning/zones/`. Each file must contain an object with `zone_id` (string), `zone_tier` (one of the three tier names), and optional `description` (ignored). The catalog is the sorted list of `zone_id` values. If two files share the same `zone_id`, the task data is invalid; this dataset has no duplicates.

Enumerate every file `*.json` directly under `/app/zoning/rules/`. Each file contains an object with array `rules`. Concatenate every `rules` array in ascending filename order to form the baseline rule list before incidents.

## Baseline rule shape

Each baseline rule is an object with: `rule_id` (string), `audit_tier` (tier name), `priority` (non-negative integer; smaller means stronger), `action` (`allow` or `deny`), `src_zones` (array of zone ids or the literal string `*` as the sole element meaning any source zone), and `dst_zones` (same pattern for destinations). A baseline rule is **invalid** if any zone token appearing in `src_zones` or `dst_zones` is neither `*` nor a `zone_id` present in the catalog. Invalid rules are omitted from matching and their `rule_id` values appear in `summary.invalid_rule_refs` sorted lexicographically without duplicates.

## Incident stream

Read `/app/zoning/incident_log.json` object key `incidents` as an array in file order. Let `SUPPORTED` be the set `{"suspend_rule", "remap_zone_tier", "inject_allow", "emergency_surface_deny"}`. An incident is **eligible** when `accepted` is true, its `day` is less than or equal to `current_day`, and its `kind` is in `SUPPORTED`. Incidents that fail any of those checks are **ignored** for mutation but still appear in `incident_trace.json`. Count ignored incidents in `summary.ignored_incidents` as the number of array entries that are not eligible. Additionally, collect every `kind` string for incidents that are not eligible solely because the kind is unsupported (accepted true, day within range, kind not in `SUPPORTED`) into `summary.unsupported_incident_kinds` as a sorted unique list of strings; if none, emit an empty array.

Process **eligible** incidents in ascending order by integer `day`, then ascending lexicographic `event_id`. Maintain:

1. `suspended` — a set of baseline `rule_id` strings removed by `suspend_rule`.
2. `tier_map` — starts as `zone_id -> declared zone_tier` from the catalog; each `remap_zone_tier` sets `tier_map[zone_id] = new_tier` (tiers must still be one of the three names).
3. `synthetic_rules` — a list appended to by inject and emergency incidents in processing order.

Kinds:

- `suspend_rule`: requires `rule_id`; remove that baseline id from active matching if present (no error if absent).
- `remap_zone_tier`: requires `zone_id` and `new_tier`; `zone_id` must exist in the catalog.
- `inject_allow`: requires `src_zone`, `dst_zone`, `audit_tier`, `priority`, and `event_id`; both zones must exist in the catalog. Append synthetic rule id `inj__` + `event_id` with action `allow`, matching exactly that ordered pair, `inject_kind` = `inject_allow`.
- `emergency_surface_deny`: requires `dst_zones` (non-empty array of catalog zone ids), `src_zones` (non-empty array of catalog zone ids or `["*"]`), `audit_tier`, `priority`, and `event_id`. Optional `exempt_src_zones` is an array of catalog zone ids (default empty). A cell `(src,dst)` matches when `dst` is listed in `dst_zones`, `src` is not listed in `exempt_src_zones`, and either `src_zones` is `["*"]` or `src` is listed in `src_zones`. Synthetic id is `surf__` + `event_id`, action `deny`, `inject_kind` = `emergency`.

Each synthetic carries the incident’s `audit_tier`, `priority`, and a monotonic `ordinal` equal to its zero-based index in the concatenation order of synthetics created across the whole run.

## Active rule set

Start from baseline rules that are valid, not suspended, each tagged `inject_kind` = `baseline` and `ordinal` equal to its zero-based index in the list sorted by `rule_id` ascending. Append all synthetics in creation order, preserving their `ordinal` as assigned above.

## Matching a cell

For ordered pair `(src_zone, dst_zone)` from the Cartesian product of the sorted catalog with itself, a rule matches when the cell satisfies the match predicates for that rule’s `src_zones` and `dst_zones` (or emergency exempt logic). Collect every matching rule.

Choose the winning rule by **maximum** lexicographic tuple `T = (inject_rank, tier_weight, neg_priority, ordinal, rule_id)` where:

- `inject_rank` is `0` for `baseline`, `1` for `emergency`, `2` for `inject_allow`.
- `tier_weight` is `weights[audit_tier]` from policy.
- `neg_priority` is the arithmetic negation of integer `priority` (so smaller declared priority sorts higher).
- `ordinal` is the rule’s ordinal integer.
- `rule_id` is the string id (lexicographic compare as final tie-break).

If no rule matches, the cell is **implicit**. Let `a` be `tier_map[src_zone]` and `b` be `tier_map[dst_zone]`. Look up key `a + "->" + b` in `implicit_matrix.pairs`; the verdict is that value. `winning_rule_id` is null and `implicit_key` is that lookup key.

If a rule matches, `via` is `explicit`, `verdict` equals the winning rule’s `action`, `winning_rule_id` is its `rule_id`, and `implicit_key` is null.

## Outputs under `/app/audit/`

Emit exactly five files:

1. `zone_catalog.json` — object with `zones`: array sorted by `zone_id`, each `{zone_id, declared_tier, effective_tier}` using the catalog declaration and post-incident `tier_map`.
2. `matrix_cells.json` — object with `cells`: array sorted by `(src_zone, dst_zone)` lexicographically, each `{src_zone, dst_zone, verdict, via, winning_rule_id, implicit_key}` with nulls as specified.
3. `precedence_table.json` — object with `rules`: array sorted by `rule_id` of every active rule (valid baseline not suspended, plus synthetics), each `{rule_id, audit_tier, priority, inject_kind, tier_weight, ordinal}` using the tier weight after incidents (policy file is static).
4. `incident_trace.json` — object with `events`: array sorted by `(day, event_id)` ascending, each `{event_id, kind, day, accepted, eligible, applied}` where `eligible` is boolean per the eligibility test above, and `applied` is true only when `eligible` is true (meaning the mutating kinds actually ran).
5. `summary.json` — object with keys `audit_version`, `current_day`, `zone_count`, `cell_count`, `verdict_counts` object with integer counts `allow` and `deny` over all cells, `ignored_incidents` integer, `unsupported_incident_kinds` array of strings sorted, and `invalid_rule_refs` array sorted.

All five files must end with a single trailing newline after the root JSON value.
