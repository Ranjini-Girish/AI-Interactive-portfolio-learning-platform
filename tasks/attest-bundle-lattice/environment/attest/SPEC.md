# Attestation bundle lattice — normative specification

All paths are under `/app/attest/`. Canonical JSON output uses UTF-8 with `ensure_ascii=False`, two-space indent, `sort_keys=True` at every object level, and each file ends with exactly one trailing newline.

## Inputs

Read `pool_state.json` (`current_day` int, `audit_version` string), `incident_log.json` (`incidents` array), every `*.json` under `policy/`, and every `*.json` under `artifacts/`. Ignore non-JSON files. Each artifact file contains exactly one object with keys `artifact_id`, `repository`, `digest`, `deployment_tier`, `signatures` (array). `digest` and every `payload_digest` use the form `sha256:` plus 64 lowercase hex digits. `deployment_tier` is one of `production`, `staging`, `development`.

`policy/trust_graph.json` defines `max_chain_depth` (int ≥ 1), `anchor_key_ids` (array of strings), and `keys` (object mapping `key_id` to `{ "parent_key_id": string | null }`). A key is an anchor if listed in `anchor_key_ids`. Parent pointers form a directed graph; `null` parent is only valid for anchors.

`policy/identity_rules.json` maps each tier to `{ "mode": "exact_allowlist" | "suffix_allowlist" | "allow_all", "allowlist"?: array, "suffixes"?: array }`. For `exact_allowlist`, the signer email must appear in `allowlist`. For `suffix_allowlist`, the email must end with at least one entry from `suffixes` (literal suffix match). For `allow_all`, identity checks pass whenever key trust succeeds.

`policy/predicate_gates.json` contains `requires_material_witness` (array of predicate type strings). When a signature’s `predicate_type` appears in that array, every digest in `referential_material_digests` (array of digest strings) must equal the `digest` field of some artifact object across the entire fleet (union of all artifact files), otherwise the signature fails with `material_missing`.

Each signature object contains `signature_id`, `key_id`, `signer_email`, `payload_digest`, `predicate_type`, `policy_rank` (int; smaller is higher priority), `referential_material_digests` (array, may be empty).

## Incident model

Supported kinds: `revoke_key`, `ban_email_pattern`, `quarantine_artifact`, `reparent_delegation`. An incident is eligible when `accepted` is true, `day` ≤ `current_day`, and `kind` is supported. Sort eligible incidents by ascending `(day, event_id)` and apply in that order to a mutable working state:

- `revoke_key`: add `key_id` to a revoked set (latest duplicate kind for the same `key_id` still just adds once; revokes are sticky across duplicates).
- `ban_email_pattern`: add `pattern` string to an active ban list (accumulate all accepted bans).
- `quarantine_artifact`: add `artifact_id` to a quarantine set.
- `reparent_delegation`: set `parent_key_id` override for `key_id` to the incident’s `new_parent_key_id` (string or JSON null). Latest incident for the same `key_id` wins; compare by later `(day, event_id)` in the sorted order.

Incidents with unsupported kinds, `accepted=false`, or `day` > `current_day` are ignored. `unsupported_incident_kinds` in the summary collects distinct kinds among incidents that are ignored solely because the kind is unsupported while `accepted=true` and `day` ≤ `current_day`.

## Key trust evaluation

After applying overrides, for each `key_id` present anywhere in signatures or `keys`, compute delegation status by walking `parent_key_id` pointers from that key: if a key repeats on the walk before reaching an anchor, status is `delegation_cycle`. If walk length exceeds `max_chain_depth` edges without hitting an anchor, `depth_exceeded`. If walk terminates at `null` without hitting an anchor, `untrustable_root`. If an anchor is reached within depth, `anchor_ok`. Anchor keys ignore parent overrides if any; anchors always report `anchor_ok` with `chain_edges=0`.

## Per-signature evaluation order on an artifact

Consider signatures in ascending `signature_id` order for tie-breaking only; outputs must sort rows by `(artifact_id, signature_id)`. Evaluation precedence for `outcome` (first match wins):

1. If artifact is quarantined: `quarantine_artifact` for every signature.
2. Else if `payload_digest` ≠ artifact `digest`: `digest_mismatch`.
3. Else if `key_id` ∈ revoked set: `revoked_key`.
4. Else if signer email matches any ban pattern: `ban_hit`. Pattern rules: if `pattern` contains no `*`, equality on full email. If `pattern` begins with `*`, require `email.endswith(pattern[1:])`. Other patterns are invalid; incidents carrying them must not add anything to the ban list.
5. Else compute key status for `key_id`; map `untrustable_root` to outcome `untrusted_key`, `delegation_cycle` → `delegation_cycle`, `depth_exceeded` → `depth_exceeded`. If status is `anchor_ok`, walk the same parent chain again and if any visited key (including the starting `key_id`) appears in the revoked set, use `revoked_key` instead of continuing.
6. Else apply identity rule for `deployment_tier`; on failure `identity_blocked`.
7. Else if predicate requires witness and any material digest is absent from the fleet digest set: `material_missing`.
8. Else `verified_ok`.

Fleet digest set is the set of all artifact `digest` strings.

## Artifact rollup

For each artifact, `final_verdict` equals `verified_ok` if any signature on that artifact evaluates to `verified_ok`; otherwise `final_verdict` is the outcome of the signature with lexicographically smallest `signature_id` among that artifact’s signatures (precedence list above already defined deterministic per-signature outcomes). `winning_signature_id` is the `signature_id` of the winning verified signature chosen by smallest `policy_rank`, then smallest `signature_id` among verified signatures; if none verified, `null`.

## Outputs under `/app/audit/`

1. `artifact_catalog.json`: `{ "artifacts": [...] }` sorted by `artifact_id`. Each row: `artifact_id`, `repository`, `digest`, `deployment_tier`, `final_verdict`, `winning_signature_id` (string or null), `quarantined` (bool).

2. `signature_outcomes.json`: `{ "signatures": [...] }` each row `artifact_id`, `signature_id`, `key_id`, `signer_email`, `predicate_type`, `policy_rank`, `outcome`.

3. `delegation_audit.json`: `{ "keys": [...] }` sorted by `key_id`. Fields: `key_id`, `effective_parent_key_id` (null or string after overrides), `delegation_status` (`anchor_ok`, `delegation_cycle`, `depth_exceeded`, `untrustable_root`), `chain_edges` (int, number of parent hops examined on the reporting walk from the key until the status decision; for anchors use 0).

4. `incident_trace.json`: `{ "events": [...] }` one row per incident in original file order with fields `event_id`, `day`, `kind`, `accepted`, `ignored_reason` (`eligible` or a snake_case token: `future_day`, `rejected`, `unsupported_kind`), `applied` (bool, true only for eligible supported rows).

5. `summary.json`: top-level keys sorted: `audit_version`, `artifact_count`, `current_day`, `ignored_incidents`, `signature_rows`, `unsupported_incident_kinds` (sorted array of strings), `verdict_counts` (object mapping each distinct `final_verdict` across artifacts to counts), `quarantined_artifacts`.

`verdict_counts` must include every final verdict present in the catalog with int ≥ 1, and no extra keys.
