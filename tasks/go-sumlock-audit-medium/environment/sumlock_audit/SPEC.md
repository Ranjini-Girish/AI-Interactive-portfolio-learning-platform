# sumlock_audit SPEC

Audit root: `/app/sumlock_audit`. Report: `/app/out/sumlock.json`. Inputs are read-only.

## Input grammar

UTF-8 text. `#` comments at column 0 ignored. Keys use `KEY: value`; repeatable keys allowed.

### workspace.wk

- `ACTIVE_PROFILES`: comma-separated profile tags.
- `AUDIT_MODE`: `strict` or `lenient`.

### policies/lenient.pol

- `FORCE_LENIENT`: `true` or `false`. When `true`, audit mode is lenient even if `workspace.wk` says `strict`.

### manifests/*.mft

- `MODULE`: module path (unique target name).
- `PRIORITY`: integer; highest `PRIORITY` per `MODULE` wins; ties break by lexicographically smaller filename.
- `TAGS`: optional comma-separated tag set.
- `ENTRY`: zero or more allowed version strings for that module.
- `DEPENDS`: zero or more other module paths.

### sources/*.src

- `SOURCE`: label string.
- `USE`: repeatable `MODULE VERSION` pair (two tokens).

### sumdb/*.sum

- `MODULE`, `VERSION`, `BLOB` (filename under `blobs/`), `HASH` (lowercase hex SHA-256 of `/app/sumlock_audit/blobs/BLOB`).

## Active modules (Twist 1)

Let `P` be tags from `ACTIVE_PROFILES`. A module is inactive when its winning manifest has `TAGS` not a subset of `P`. Untagged modules are always active. Inactive modules appear only in `excluded`.

## Priority ownership (Twist 2)

For each `MODULE`, the winning manifest defines owned `ENTRY` versions only. For each `USE` line on an active module, if the version is not owned, emit `unknown_version`.

## Sum checks (Twist 3)

For each active `USE` with owned version: if no `sumdb` record for that pair, emit `missing_sum`; if `HASH` differs from blob SHA-256, emit `stale_sum`.

## Orphan sums (Twist 3b)

In strict audit mode, each sumdb record on an active module whose pair is not referenced by any `USE` line emits `orphan_sum` with empty `source`.

## Module cycles (Twist 3c)

Among active modules, edge `A -> B` when winning manifest for `A` lists `DEPENDS: B` and `B` is active. Normalize cycles (smallest module path first), sort by first element. For each edge on a cycle, emit `module_cycle` with `module=A`, `version=B`, `source=""`.

## Lenient mode (Twist 4)

Lenient when `FORCE_LENIENT` is `true` or `AUDIT_MODE` is `lenient`. In lenient mode, do not emit `orphan_sum`; other rules apply.

## Output schema

Top-level keys: `excluded`, `modules`, `violations`, `cycles`, `summary` with fields as in instruction.md. Violations sorted by `code`, `module`, `source`, `version`. Modules sorted by `module`. Encoding: two-space indent, sorted keys, compact separators, no trailing newline.
