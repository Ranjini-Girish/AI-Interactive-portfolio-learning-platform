# CSP merge policy audit

Normative inputs live under the cspmerge bundle root beside this file. Emit five UTF-8 JSON documents under the audit directory with no byte-order mark.

## Canonical JSON

Every output file MUST be serialized with `sort_keys=true`, `indent=2`, `separators=(",", ": ")`, `ensure_ascii=true`, and exactly one trailing newline (`0x0a`) after the closing brace or bracket.

## Primary inputs

Read `pool_state.json`, `policy.json`, `inheritance.json`, `incident_log.json`, every `*.json` directly under `origins/`, and every `*.json` directly under `bundles/`. Ignore `ledger/`, `ancillary/`, and `anchors/` for semantics.

### pool_state.json

- `current_day` (integer): evaluation day for incidents and report budgets.

### policy.json

- `pinned_directives` (array of strings): directive names that cannot be replaced once first assigned during bundle merge for an origin.
- `report_caps` (object): maps tier (`gold`|`silver`|`bronze`) to a non-negative integer daily report budget.
- `supported_kinds` (array of strings): incident kinds the audit understands.

### inheritance.json

- `edges` (array): objects `{parent, child}` with string fields. The graph is acyclic. An origin is a descendant of `ancestor` when a directed path of `parent` to `child` edges exists from `ancestor` to that origin.

### Origin files

Each file has `origin_id` (unique string) and `tier` (`gold`|`silver`|`bronze`).

### Bundle files

Each file has `bundle_id` (unique string), `origin_id` (string), `delivery_mode` (`enforce`|`report-only`), `directives` (object mapping directive name to array of source tokens), and optional `nonces` (array of strings, default empty).

Malformed bundles (unknown `delivery_mode`, empty `bundle_id`, duplicate `bundle_id`, unknown `origin_id`) MUST make the audit exit non-zero.

### incident_log.json

`events` is an array of objects with `event_id`, `day`, `accepted` (boolean), `kind`, and `payload` (object). Sort processing order by `(day ascending, event_id ascending)`.

For each event compute `resolution`:

- `ignored_future_day` when `day > current_day`
- `ignored_not_accepted` when `accepted` is false
- `ignored_unsupported_kind` when `kind` is not listed in `supported_kinds`
- `applied` otherwise

Only `applied` events mutate mutable state.

Mutable per-origin state (initially `quarantined=false`, `frozen_max_bundle_id=null`, `report_uses=0`):

- `origin_compromise`: payload `origin_id` string. Set `quarantined=true` for that origin and every descendant in `inheritance.json`.
- `directive_freeze`: payload `origin_id` and `max_bundle_id` string. Set `frozen_max_bundle_id` to that string (overwrites prior freeze for the same origin).
- `csp_report`: payload `origin_id`. When the origin is not quarantined, increment `report_uses` by 1.
- `audit_review`: payload `origin_id` and `target_posture` equal to one of `enforce`|`report-only`|`report_suppressed`. Record the latest review target per origin (last applied event wins).

## Bundle merge per origin

Group bundles by `origin_id`. Consider only bundles whose `origin_id` exists. Sort bundles ascending by `bundle_id`.

When `frozen_max_bundle_id` is non-null for an origin, ignore any bundle whose `bundle_id` is lexicographically greater than `frozen_max_bundle_id`.

Walk bundles in order. For each directive name present in the bundle:

- If the directive is already present in the working map and the name is listed in `pinned_directives`, skip this bundle contribution for that directive.
- Otherwise merge into the working map entry:
  - If no entry exists, set sources to the bundle list and remember the bundle `delivery_mode`.
  - If an entry exists and the new bundle `delivery_mode` is `enforce` while the stored mode is `report-only`, replace sources and mode with the new bundle values.
  - If stored mode is `enforce` and the new bundle is `report-only`, keep the stored entry.
  - If both modes are equal, replace sources and mode with the new bundle (later `bundle_id` wins).

After all bundles for the origin are merged, normalize each directive source list:

1. Remove duplicate tokens (keep first occurrence order before sorting).
2. Sort tokens ascending by Unicode code point.
3. If any token begins with `sha256-`, `sha384-`, or `sha512-`, or begins with `nonce-`, remove every `unsafe-inline` token.

Quarantined origins MUST emit an empty `effective_directives` object regardless of bundles.

## Nonce collisions

Collect every `nonces` entry across all bundles (all origins). For each nonce string used by more than one distinct `origin_id`, emit one collision row. Ignore quarantined origins when building collision membership.

## Enforce posture

For each origin sorted by `origin_id`:

- `preliminary_posture`:
  - `blocked_quarantine` when quarantined.
  - `enforce` when the merged map contains at least one directive whose winning delivery mode was `enforce`.
  - `report_suppressed` when not quarantined, no enforce-winning directive exists, and `report_uses` is strictly greater than `report_caps[tier]`.
  - `report-only` otherwise (report-only bundles only and within cap).

- `delivery_posture` begins as `preliminary_posture`. When a latest `audit_review` target exists for the origin, replace `delivery_posture` with that target. Map JSON `report-only` review target to output string `report-only` (hyphenated).

- `review_override_applied` is true exactly when an `audit_review` event was applied for that origin.

## Outputs

### directive_matrix.json

Keys: `current_day`, `origins` (array sorted by `origin_id`). Each origin object contains `effective_directives` (object with directive names sorted as keys, each value a sorted source array), `origin_id`, `quarantined` (boolean).

### nonce_collisions.json

Keys: `collisions` (array sorted by `nonce` ascending). Each object: `nonce`, `origin_ids` (distinct origin ids sorted ascending).

### enforce_verdicts.json

Keys: `origins` (sorted by `origin_id`). Each object: `delivery_posture`, `origin_id`, `preliminary_posture`, `review_override_applied` (boolean).

### incident_overrides.json

Keys: `events` (processing order). Each object: `accepted`, `day`, `event_id`, `kind`, `resolution`.

### summary.json

Keys (all integers unless noted): `applied_incidents`, `audit_version` (must be 1), `bundle_count`, `collision_count`, `current_day`, `enforce_posture_origins` (count with `delivery_posture` equal to `enforce`), `ignored_counts` (object with keys `ignored_future_day`, `ignored_not_accepted`, `ignored_unsupported_kind`, each integer), `origin_count`, `quarantined_origins`, `report_suppressed_origins`, `review_override_origins`.

## Tooling contract

Read bundle root from `CMP_DATA_DIR` defaulting to `/app/cspmerge`. Write outputs to `CMP_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing. Never mutate inputs.
