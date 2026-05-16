# OAuth Client Lattice Audit — Normative Specification

All paths below are inside `/app/oauthlattice/`. Emit five UTF-8 JSON documents under `/app/audit/` using `json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False)` plus exactly one trailing newline. Every list that is not explicitly keyed by an identifier must be sorted ascending by Unicode code point of the JSON string form of each element when the element is an object (sort keys recursively inside the stringification), except where this document names an explicit alternate sort key.

## Inputs

Read `pool_state.json` for integer `current_day`. Read `incident_log.json` for array `events` (each has string `event_id`, integer `day`, boolean `accepted`, string `kind`, object `payload`). Read `policy/supported_kinds.json` for array `kinds`. Read `policy/grant_caps.json` for object `caps` mapping tier (`gold`|`silver`|`bronze`) to object mapping `client_type` (`public`|`confidential`) to array of allowed grant type strings. Read `policy/scope_implications.json` for array `edges` of objects `{parent, child}` with string fields. Read `policy/tier_rules.json` for objects `redirect_mode` (tier to one of `exact`|`prefix`|`prefix_or_localhost_public`) and `pkce_for_auth_code` (tier to object mapping `client_type` to one of `required`|`relaxed`). Read every `clients/*.json` (object with `client_id`, `client_type`, `tier_declared`, array `grant_types`, array `redirect_uris`, array `registered_scopes`). Read every `resources/*.json` (`resource_id`, array `required_scopes`). Read every `bindings/*.json` (`binding_id`, `client_id`, `resource_id`, `requested_redirect`).

## Incident resolution

Build the list of events sorted by `(day ascending, event_id ascending)`. For each event compute `resolution` as follows: if `day` is greater than `current_day`, `ignored_future_day`. Else if `accepted` is false, `ignored_not_accepted`. Else if `kind` is not an element of `supported_kinds.json` kinds, `ignored_unsupported_kind`. Else `applied`. Only `applied` events mutate mutable state described below; others are recorded in the trace only.

Mutable state is per `client_id` string: `tier_override` (initially null), `quarantine` (initially false), `revoked_scopes` (set, initially empty), `pinned_redirects` (set, initially empty). Process `applied` events in sorted order:

- `client_quarantine`: payload must contain `client_id` string and boolean `active`. Set that client’s `quarantine` to `active`.
- `scope_revoke`: payload contains `client_id` and array `scopes`. Add every scope string to `revoked_scopes` for that client (set union).
- `redirect_pin`: payload contains `client_id` and string `redirect_uri`. Insert `redirect_uri` into `pinned_redirects` for that client.
- `tier_override`: payload contains `client_id` and string `new_tier` equal to one of `gold`|`silver`|`bronze`. Set `tier_override` to `new_tier`.

## Derived client fields

For each client file sorted by `client_id`:

- `effective_tier` is `tier_override` when non-null, otherwise `tier_declared`.
- `effective_redirect_uris` is the sorted unique union of the client’s `redirect_uris` and that client’s `pinned_redirects`.
- If `quarantine` is true, `effective_scopes` is the empty array. Otherwise start from the sorted set difference `registered_scopes minus revoked_scopes`, then compute the closure under `edges`: whenever `parent` is present, ensure `child` is present; repeat until no new child appears. Emit `effective_scopes` sorted.
- `illegal_grants` is the sorted list of entries in `grant_types` that are not members of `caps[effective_tier][client_type]`. If `grant_types` is empty, `illegal_grants` is empty.
- `pkce_posture`: if `authorization_code` is not in `grant_types`, emit `pkce_not_applicable`. Else map `(effective_tier, client_type)` through `pkce_for_auth_code`; emit `pkce_required` when the table says `required`, `pkce_relaxed` when it says `relaxed`.

## Redirect verdict for a binding

If the client id is unknown, verdict `blocked_unknown_client` with `matched_rule` null. If that client’s `quarantine` is true, verdict `blocked_quarantine`, `matched_rule` null. Otherwise read `redirect_mode[effective_tier]` as `mode`.

- `exact`: verdict `allowed_exact` when `requested_redirect` equals some element of `effective_redirect_uris`; else `blocked_not_listed`.
- `prefix`: verdict `allowed_prefix` when there exists `u` in `effective_redirect_uris` such that `requested_redirect == u` OR (`requested_redirect` has length greater than `u` AND `requested_redirect` begins with `u` AND the next character in `requested_redirect` is `/`); when multiple `u` qualify, choose the longest `u` by character length, ties broken by ascending Unicode compare of `u`. Set `matched_rule` to that `u` for `allowed_prefix` or `allowed_exact` (exact is also a prefix with length equality). If none qualify, `blocked_not_listed` with null `matched_rule`.
- `prefix_or_localhost_public`: first evaluate the `prefix` rule; if it succeeds, use that verdict and `matched_rule`. Else if `client_type` is `public` and `requested_redirect` matches the regular expression `^http://127\.0\.0\.1:\d+/` OR `^http://localhost:\d+/`, verdict `allowed_localhost_public` with `matched_rule` set to the literal string `localhost_exception`. Otherwise `blocked_not_listed`.

## Resource access for a binding

If client unknown: `resource_access` is `deny` with `deny_reason` `unknown_client`. If quarantined: `deny` with `quarantined`. Else if every element of the resource’s `required_scopes` is contained in `effective_scopes`, `allow` with `deny_reason` null. Else `deny` with `missing_scope`.

## Output shapes

`client_posture.json` top-level key `clients`: array sorted by `client_id` of objects with keys `client_id`, `client_type`, `effective_redirect_uri_count` (integer length of `effective_redirect_uris`), `effective_scopes`, `effective_tier`, `illegal_grants`, `pkce_posture`, `quarantined` (boolean), `registered_scope_count` (length of original `registered_scopes` from file).

`binding_access.json` top-level `bindings`: sorted by `binding_id`, objects with `binding_id`, `client_id`, `deny_reason` (null or string), `resource_access` (`allow`|`deny`), `resource_id`.

`redirect_eval.json` top-level `redirects`: sorted by `binding_id`, objects with `binding_id`, `matched_rule` (string or null), `verdict` (string).

`incident_trace.json` top-level `events`: same sort as processing, each object keys `accepted`, `day`, `event_id`, `kind`, `resolution`.

`summary.json` keys: `applied_incidents` (count of applied), `audit_version` (integer 1), `binding_count`, `client_count`, `current_day`, `ignored_counts` (object with keys `ignored_future_day`, `ignored_not_accepted`, `ignored_unsupported_kind` mapping to integers), `illegal_grant_clients` (count of clients whose `illegal_grants` is non-empty), `localhost_redirect_matches` (count of `allowed_localhost_public` verdicts), `prefix_redirect_matches` (count of `allowed_prefix` verdicts), `quarantined_clients` (count of clients with `quarantined` true after processing), `resource_allow_total` (bindings with `allow`), `resource_deny_total`.

All integer counts are non-negative. `ignored_counts` must include every ignored resolution key even when zero.
