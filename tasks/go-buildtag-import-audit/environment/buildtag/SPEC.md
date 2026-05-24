# Build-tag import audit (normative)

This document is the single source of truth for `/app/buildtag/` inputs and `/app/outcome/` outputs. Read it completely before coding.

## Literals (copy exactly into JSON)

- `package_status.status` must be one of: `active_ok`, `active_violation`, `excluded`, `import_cycle`.
- `incidents.kind` must be one of: `forbidden_waiver`, `tag_injection`.

## Input layout

- `context.json` fields: `goos` (string), `goarch` (string), `extra_tags` (array of strings), `entry_points` (array of import paths), `reference_day` (integer calendar day).
- `pool_state.json` fields: `masked_tags` (array of strings; may be empty).
- `policy.json` fields: `forbidden_imports` (array of exact import path strings).
- `incidents.json` is an array of objects, each with: `day` (int), `event_id` (string), `accepted` (bool), `kind` (string), `payload` (object).
- `packages/*.json` each describe one package: `package_key` (string), `package_path` (string), `files` (array). Each file has `name` (string), `cnf` (array of arrays of strings), `imports` (array of strings). An empty `cnf` array means the file is always eligible when no ignore rule fires.

## Ignore rule

If any OR-clause inside `cnf` is exactly the one-element list `["ignore"]` (only that literal), the file is permanently excluded regardless of tags.

## Tag universe

Let `T` be a set of strings built in this order:

1. Add `strings.ToLower(context.goos)` and `strings.ToLower(context.goarch)`.
2. Append every element of `context.extra_tags` verbatim (no case folding).
3. If `strings.ToLower(context.goos)` is one of `linux`, `darwin`, `freebsd`, `openbsd`, `netbsd`, add literal tag `unix`.
4. Consider incidents in ascending `day`, then ascending `event_id`. Keep only those with `accepted == true` and `day <= context.reference_day`. For each remaining incident with `kind == tag_injection`, append every string in `payload.tags` preserving order within that incident; later incidents append after earlier ones.
5. Remove every tag that appears in `pool_state.masked_tags` (exact string match after incident tags are applied). Removing a tag that is not present is a no-op.

## CNF evaluation

Each inner array is an OR-clause. The outer array is AND across clauses. A clause is satisfied if at least one of its literals evaluates true. An empty outer `cnf` is satisfied.

A literal is either `NAME` or `!NAME` where `NAME` has no leading `!`. For `NAME`, the literal is true when `NAME` is a member of `T`. For `!NAME`, the literal is true when `NAME` is not a member of `T`.

A file is **active** when it is not excluded by the ignore rule and its `cnf` is satisfied.

## Import resolution

Build a map from `package_path` to `package_key` using every package file. An import string `imp` resolves to `package_key` when some loaded package has `package_path == imp`. Unresolved imports are ignored for graph edges but still count toward forbidden detection when `imp` equals an entry in `policy.forbidden_imports`.

## Forbidden waiver

After incident filtering, consider every `forbidden_waiver` incident with `accepted == true` and `day <= context.reference_day`. Each such row supplies `payload.import_path`. When several rows list the same path, the incident with the larger `day` wins; tie-break by lexicographically larger `event_id`. The winning row removes that exact path from forbidden checks for all active-file import edges.

## Active imports and package graph

For each active file, each entry in its `imports` array is one directed edge from the file’s package `package_key` toward the resolved target `package_key` when resolution succeeds. Self-edges are allowed. Collapse parallel edges; the report lists each `(from_key, to_key, import_path)` triple once. Sort triples by `from_key`, then `to_key`, then `import_path`.

An **active package** has at least one active file. Otherwise it is `excluded`.

## Package status precedence

Compute on the subgraph induced by active packages and edges whose targets resolved to an active package (drop edges to unresolved externals for cycle detection only; still evaluate forbidden on every import string from active files).

1. If the package has no active files → `excluded`.
2. Else if any active file imports a string listed in `policy.forbidden_imports` and that string is not waived → `active_violation`.
3. Else if the package’s `package_key` participates in any directed cycle within the active induced subgraph (length ≥ 1 self-loop counts) → `import_cycle`.
4. Else → `active_ok`.

When both (2) and (3) could apply, `active_violation` wins.

## Entry closure

For each path `p` in `context.entry_points` in given order: if no package has `package_path == p`, emit `excluded_entry: true` and `reachable_package_keys: []`. If that package is `excluded`, emit `excluded_entry: true` and `reachable_package_keys: []`. Otherwise `excluded_entry: false` and list every `package_key` reachable from that package’s key following directed edges on the active induced subgraph (including the start key), sorted uniquely ascending by `package_key`.

## Output files (UTF-8 JSON under `/app/outcome/`)

Canonical encoding for every file: `json.MarshalIndent` in Go with indent two spaces, keys sorted lexicographically at every object level, slice and map keys sorted as described below, and exactly one trailing newline `\n` after the closing brace or bracket. Arrays of objects must be sorted by the sort keys listed per file.

### `active_sources.json`

Object keys: `rows`. `rows` is an array of objects with keys `file`, `package_key`, `package_path`. Sort by `(package_key, file, package_path)`.

### `resolved_import_edges.json`

Object keys: `edges`. Each edge object has `from`, `import_path`, `to`. Sort the array by `(from, to, import_path)`. `to` is the resolved target `package_key`, only present for resolved edges (omit unresolved — do not list edges whose import does not resolve).

### `package_status.json`

Object keys: `packages`. Each object has `package_key`, `package_path`, `status`. Sort by `package_key`.

### `entry_closure.json`

Object keys: `entries`. Each object has `entry_path`, `excluded_entry` (bool), `reachable_package_keys` (array of strings sorted ascending). Sort `entries` by `entry_path`.

### `summary.json`

Object keys only these integers, and they must appear in this exact key order: `active_files_total`, `active_packages_total`, `edges_resolved_total`, `entries_excluded_total`, `forbidden_edges_raw_total`, `forbidden_edges_waived_total`, `incidents_applied_total`, `packages_active_ok_total`, `packages_active_violation_total`, `packages_excluded_total`, `packages_import_cycle_total`, `packages_total`.

Definitions:

- `packages_total`: count of loaded package JSON files.
- `active_files_total`: count of active files.
- `active_packages_total`: packages not `excluded`.
- `packages_excluded_total`: status `excluded`.
- `packages_active_ok_total`, `packages_active_violation_total`, `packages_import_cycle_total`: counts matching each status.
- `edges_resolved_total`: count of rows in `resolved_import_edges.edges`.
- `forbidden_edges_raw_total`: count of import strings from active files that equal some `policy.forbidden_imports` entry before waiver.
- `forbidden_edges_waived_total`: among those raw hits, how many are waived after waiver resolution.
- `incidents_applied_total`: count of objects in `incidents.json` with `accepted == true` and `day <= context.reference_day` (see detail section below).
- `entries_excluded_total`: number of `entry_closure.entries` with `excluded_entry == true`.

## `incidents_applied_total` detail

Count every incident that satisfies `accepted == true` and `day <= context.reference_day` exactly once toward `incidents_applied_total`, regardless of `kind`.
