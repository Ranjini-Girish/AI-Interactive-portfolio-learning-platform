# WASM capability lattice audit

Inputs live beside this file. Read `policy.json`, `pool_state.json`, `incident_log.json`, `reexports.json`, every `allowlists/*.json`, every `modules/*.json`, and every `hosts/*.json`. Files under `ledger/` are packaging only.

## Canonical JSON

Emit every artifact as JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Policy

- `cap_rank` is an ordered array of capability strings. Earlier entries outrank later ones when two capabilities share the same category prefix (substring before the first `.` character, or the whole string when no dot exists).
- `supported_incident_kinds` lists incident kinds the journal accepts.
- `import_deny_substrings` lists substrings; any import containing one is denied before allowlist checks.

## Pool state

- `current_day` gates incidents: only events with `day <= current_day` are eligible.

## Module files

Each module JSON has `module_id`, `tier` (`gold`|`silver`|`bronze`), `declared_imports` (array of strings), and `capabilities` (array of strings). `module_id` values are unique.

## Allowlists

Each `allowlists/<tier>.json` has `prefixes`, an array of strings. An import is allowlisted for tier T when it starts with at least one prefix listed for T.

## Re-exports

`reexports.json` has `links`, an array of `{from, to, prefix_filters}`. For link L, every import I in the effective import set of module `from` that starts with at least one string in `prefix_filters` is also required of module `to` unless `to` is quarantined before evaluation.

Compute `effective_imports(M)` iteratively:

1. Start with the declared import set of M.
2. Repeatedly add filtered exports from every link whose `to` equals M until a full pass adds nothing.
3. Sort the final set ascending by Unicode code point.

## Host slots

Each `hosts/*.json` has `host_slot` (string) and `members` (array of module_id strings). Members must exist. A module belongs to at most one host file.

For each host slot, build `merged_capabilities`:

1. Collect every capability listed on non-quarantined members after incident processing.
2. Group capabilities by category prefix.
3. Within each category, keep exactly one capability: the highest-ranked member of `cap_rank` present in that category (smallest index). If none appear in `cap_rank`, keep the ASCII-smallest capability string in that category.
4. Sort the surviving capabilities ascending.

## Incidents

Each event has `day`, `event_id`, `kind`, and `accepted` (default true). Reject when `accepted` is false (`reason=accepted_false`), when `day > current_day` (`reason=future_day`), or when `kind` is unsupported (`reason=unsupported_kind`). Accepted events apply in ascending `(day, event_id)` order:

- `module_compromise` with `scope.module_id` quarantines that module and every module reachable by following `links` forward from the compromised id (`from` to `to`) any number of times.
- `capability_revoke` with `scope.capability` removes that exact capability string from every non-quarantined module's local capability list before host merge.
- `import_freeze` with `scope.module_id` marks the module frozen: after effective imports are computed, if any effective import is not also in the module's declared list, the module verdict becomes `import_frozen`.

Quarantined modules always have verdict `quarantined`, empty effective imports, and do not contribute capabilities to host merge.

## Import verdict per module

Evaluate non-quarantined modules in ascending `module_id` order:

1. If frozen and effective imports are not a subset of declared imports, verdict `import_frozen`.
2. Else if any effective import contains a deny substring, verdict `import_denied`.
3. Else if any effective import is not allowlisted for the module tier, verdict `import_denied`.
4. Else verdict `ok`.

## Outputs

Write five files to the audit directory:

1. `module_verdicts.json` with keys `modules` then `evaluation_day`. Each row has `declared_imports`, `effective_imports`, `module_id`, `tier`, and `verdict`. Sort rows by `module_id` ascending.
2. `import_closure.json` with `closures` mapping each module_id to its sorted effective import array. Keys sorted lexicographically.
3. `capability_lattice.json` with `host_slots` mapping each host_slot to `{host_slot, merged_capabilities, members}` sorted by `host_slot`. `merged_capabilities` sorted ascending.
4. `incident_journal.json` with `accepted` and `ignored` arrays sorted by `(day, event_id)`.
5. `summary.json` with `evaluation_day`, `host_slots_total`, `modules_total`, `service_tiers` (fixed `["bronze","gold","silver"]`), and `verdict_counts` (keys sorted lexicographically).

## Tooling

Read `WCA_DATA_DIR` defaulting to `/app/wasmcaps` and `WCA_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
