# Struct Tag Matrix Audit Specification

Normative contract for the read-only registry under `/app/registry/`, five audit
JSON files under `/app/audit/`, canonical encoding, and incident handling.

## Normative literals (read first)

- Any field whose package has an **accepted** `integrity_lock` incident winner
  must list `effective_severity` = **`blocked`** in `tag_parse_matrix.json`
  even when tag parsing succeeded and no collision exists.
- Any field with `naming_skew` true whose package has an **accepted**
  `naming_waiver` incident winner must use **`info`** (not `warn`) for
  `effective_severity` when the only non-ok contributors are that skew and no
  parse failure or collision applies.

## Inputs (under `/app/registry/`)

- `/app/registry/pool_state.json` — `{ "current_day": int }`.
- `/app/registry/policy/policy.json` — `{ "supported_incident_kinds": [ ... ] }` sorted ASCII.
- `/app/registry/incidents/incident_log.json` — `{ "events": [ ... ] }` each event
  `{ "event_id", "kind", "package_id", "day", "accepted" }`.
- `/app/registry/packages/<file>.json` — `{ "package_id", "module_path", "structs": [ {
  "struct_id", "fields": [ { "field_id", "go_name", "tags": { ... } } ] } ] }`.
  Tag values mirror Go struct tag string bodies (for example `id,omitempty`).

## Tag parsing

For each `json` or `bson` tag string on a field: split on ASCII comma `,` into
segments; trim ASCII spaces on every segment. The first segment is the
**primary name**. Remaining segments are **flags** (lowercase compared).
Allowed `json` flags: `omitempty`, `string`. Allowed `bson` flags: `omitempty`
only. Unknown flag tokens make `parse_status` = `invalid_unknown_json_flag` or
`invalid_unknown_bson_flag` respectively. Empty primary after trimming yields
`invalid_empty_json_name` or `invalid_empty_bson_name`. Missing `json` key under
`tags` yields `parse_status` = `missing_json_tag`. Otherwise `parse_status` =
`ok`. Primary exactly `-` marks `serialization_ignored` true for JSON; such
fields are excluded from JSON name collision grouping.

## Naming skew

When both `json` and `bson` tags parse successfully, neither primary is `-`,
and primaries differ (case sensitive), set `naming_skew` true for that field.

## JSON name collisions

Within one `(package_id, struct_id)`, group fields that share the same JSON
primary (case sensitive), ignoring ignored or non-ok parses. Groups with two or
more members are collisions; every member field is treated as collision-bearing
for severity (error unless blocked by lock).

## Incident resolution

Consider events in any order, then apply filters. Ignore with implicit reasons
captured only via `ignored_event_ids` when: `accepted` is false; `day` exceeds
`current_day`; `kind` not listed in `supported_incident_kinds`. Partition
remaining events by `(kind, package_id)`. Within each partition choose exactly
one **winner**: largest `day`, tie-break ASCII-smallest `event_id`. Every other
partition member is superseded. Emit every ignored `event_id` ASCII-sorted in
`incident_resolution.json`. Emit `accepted_events` sorted by `event_id`, each
object keys sorted with `day`, `event_id`, `kind`, `package_id`.

## Severity aggregation

Per-field `effective_severity` order of application: integrity lock forces
`blocked`; else any parse status other than `ok` or BSON parse failure →
`error`; else collision membership → `error`; else `naming_skew` with waiver
winner on that package → `info`; else `naming_skew` → `warn`; else `ok`.

## Package rollups

`packages` sorted by `package_id`. Each row: `counts` with integer keys exactly
`error`, `info`, `ok`, `warn` (ASCII key order in the object) counting fields in
that package whose `effective_severity` matches, **excluding** fields counted as
`blocked` from the histogram; `highest_severity` is `blocked` when the package
has an accepted `integrity_lock` winner, otherwise the maximum of the four
histogram tiers using order `ok < info < warn < error`; `forced_by_incident`
is true only for integrity lock.

## Output shapes

**tag_parse_matrix.json** — `{ "entries": [ { "effective_severity", "field_id",
"go_name", "naming_skew", "package_id", "parse_status", "serialization_ignored",
"struct_id", "tags_normalized", "tags_raw" } ] }` sorted by `(package_id,
struct_id, field_id)`. `tags_normalized` maps `json` and `bson` each to either
`null` or `{ "flags": [...], "primary": "..." }` with sorted `flags`.

**json_name_collisions.json** — `{ "groups": [ { "field_ids", "json_name",
"package_id", "struct_id" } ] }` sorted by `(package_id, struct_id, json_name)`;
`field_ids` sorted ASCII.

**package_rollups.json** — `{ "packages": [ ... ] }` as above.

**incident_resolution.json** — `{ "accepted_events", "ignored_event_ids" }`
with `ignored_event_ids` a sorted JSON array of strings.

**summary.json** — keys exactly (ASCII sorted on disk):
`accepted_incident_events`, `blocked_packages`, `collision_groups`,
`fields_missing_json_tag`, `fields_total`, `ignored_incident_events`,
`naming_skew_fields`, `packages_total`, `parse_error_fields`, `structs_total`,
`waived_naming_skew_fields`. All non-negative integers. `parse_error_fields`
counts fields whose `parse_status` is not `ok`.

## Canonical JSON

UTF-8, two-space indent, sorted object keys at every depth, exactly one trailing
newline (`\n`).
