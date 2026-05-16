# OIDC signing key lifecycle audit

This document is normative. Treat every path as relative to the read-only corpus root directory named in the task prompt. Integer days are inclusive closed intervals on a single global day counter. ASCII order means lexicographic order of UTF-8 strings unless stated otherwise.

## Corpus layout

The corpus contains `pool_state.json`, `governance/policy.json`, `incident_log.json`, directories `published/keys/`, `staged/keys/`, and `servers/`. Each `*.json` file under `published/keys/` and `staged/keys/` holds exactly one object called a **record**. Each file under `servers/` holds one object with `server_id`, `required_audience`, and `tier` strings.

## Record fields

Every record must contain strings `record_id`, `kid`, `alg_family`, integer `sequence`, integers `not_before_day` and `not_after_day`, and array `allowed_audience_prefixes` of distinct strings sorted ascending. Missing fields make the record unusable; usable records participate in merging.

## Merge into merged keys

Enumerate published records by sorting their file paths ascending, then staged records by sorting their file paths ascending. Append staged after published while keeping each record’s **origin** tag `published` or `staged`.

For each distinct `kid`, choose exactly one winning record using this total order: larger `sequence` wins; if tied, larger `not_after_day` wins; if tied, larger `not_before_day` wins; if tied, smaller `record_id` wins; if still tied, `staged` wins over `published`. The winner defines the merged row’s `record_id`, `sequence`, bounds, prefixes, `alg_family`, and `origin`.

## Incident intake

Read `incident_log.json` field `events` as a list. An event is **eligible** when `accepted` is true, its `kind` appears inside `governance/policy.json` field `supported_incident_kinds`, and integer `day` is less than or equal to `pool_state.json` field `current_day`.

Eligible `extend_validity` events carry integer `payload.add_days` and string `payload.kid`. Eligible `revoke_key` events carry string `payload.kid` and integer `payload.effective_day`. Eligible `audience_emergency` events carry string `payload.target_server_id`, string `payload.surrogate_audience`, and integers `payload.start_day` and `payload.until_day`.

**Duplicate suppression** groups eligible events by the tuple `(kind, scope, dedup_target, day)` where `dedup_target` is `payload.kid` for `extend_validity` and `revoke_key`, and `payload.target_server_id` for `audience_emergency`. Within each group with more than one member, keep the member with the smallest `event_id` and discard the others. Discarded duplicates are counted as ignored incidents.

Kinds present on events that are not listed in `supported_incident_kinds` contribute to `summary.unsupported_kind_events` even when `accepted` is true.

## Applying extends and revokes

Let `not_after_effective` start as the merged `not_after_day`. Sort surviving `extend_validity` events by `(day asc, event_id asc)` and add each `add_days` to `not_after_effective` for its `kid`.

A `revoke_key` survivor marks its `kid` as **revoked** when `payload.effective_day` is less than or equal to `current_day`. Revocation is evaluated after extends.

## Lifecycle phases

Let `G` be `policy.overlap_tail_days` (non-negative integer). Let `nb` be `not_before_day` and `na` be `not_after_effective`. Let `cd` be `current_day`.

If a kid is revoked, its phase is `revoked_incident` and `phase_reasons` is `["revoked"]`.

Otherwise compute: if `cd < nb`, phase is `premature` with reasons `["before_not_before"]`. If `cd > na`, phase is `expired` with reasons `["after_not_after"]`. Else let `tail_start = na - G + 1`. If `cd >= tail_start`, phase is `grace_tail` with reasons `["overlap_tail"]`. Otherwise phase is `active` with reasons `["in_window"]`.

## Signing eligibility

Let `E` be the set of phase strings listed in `policy.signing_eligible_phases` preserving file order without duplicates. A merged key may participate in audience matching only when its phase is in `E`.

Prefix match rule: a key matches a string `aud` when there exists a prefix `p` in `allowed_audience_prefixes` such that `aud == p` or `aud` begins with `p` as a substring prefix match (standard string `startswith`).

## Server audience profile

For each server, determine whether an `audience_emergency` survivor targets its `server_id`. It is **active** when `start_day <= cd <= until_day`. When active, use `surrogate_audience` as the **effective audience** for matching; otherwise use `required_audience`.

Collect every signing-eligible key that matches the effective audience. Sort those kids ascending and store as `eligible_kids`.

Choose `chosen_kid`: if the list is empty, use the empty string. Otherwise pick the key that maximizes `(sequence, not_after_effective, kid)` using integer compares for the first two fields and ASCII compare for `kid`; break any residual tie by smallest `kid`.

## Pairwise overlap

For a server with at least two distinct eligible kids, consider every unordered pair. For keys `a` and `b` with intervals `[nb_a, na_a]` and `[nb_b, na_b]` using the merged `not_before_day` and final `not_after_effective`, the overlap length is `max(0, min(na_a, na_b) - max(nb_a, nb_b) + 1)` when `max(nb_a, nb_b) <= min(na_a, na_b)`, otherwise zero.

`max_pair_overlap_days` is the maximum overlap among all pairs. `witness_kids` is the two distinct kids from a attaining pair sorted ascending; when no pair exists, use an empty array.

## Outputs under `/app/audit/`

Write five UTF-8 JSON files using `json.dumps(..., sort_keys=True, indent=2, ensure_ascii=False)` plus a single trailing newline and no BOM.

### `key_lifecycle.json`

Top-level object with key `keys` only. Each element includes `kid`, `record_id`, `origin`, `sequence`, `not_before_day`, `not_after_effective`, `allowed_audience_prefixes`, `lifecycle_phase`, `phase_reasons` (array of strings sorted ascending). Sort `keys` by `kid` ascending.

### `server_bindings.json`

Top-level object with key `servers` only. Each element includes `server_id`, `tier`, `required_audience`, `effective_audience`, `emergency_active` boolean, `eligible_kids`, `chosen_kid`. Sort `servers` by `server_id` ascending.

### `overlap_report.json`

Top-level object with key `servers` only, sorted by `server_id`. Fields per row: `server_id`, `max_pair_overlap_days` integer, `witness_kids` array.

### `incident_ledger.json`

Top-level object with keys `accepted_events` and `ignored_events`, both arrays sorted by `(day asc, event_id asc)`. Each entry records `event_id`, `day`, `kind`, `scope`, and `dedup_target` string (kid or server id). `ignored_events` lists suppressed duplicates, ineligible days, `accepted=false`, unsupported kinds, and any `extend_validity` whose `kid` is unknown to merged keys after merging.

### `summary.json`

Top-level keys only: `audit_version` string copied from pool, `current_day` integer, `keys_merged_count`, `servers_scanned_count`, `accepted_incident_events`, `ignored_incident_events`, `unsupported_kind_events`, `revoked_key_count`, `active_emergency_servers`.
