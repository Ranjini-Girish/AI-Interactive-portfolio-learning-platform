This spec defines inputs under `/app/gateway/` and the required JSON report at `/app/out/gateway_audit.json`. All rules are normative.

1. Files and encoding
- All JSON is UTF-8. No BOM. CRLF is allowed in SPEC only; JSON inputs use LF.
- Ignore any file named `README.txt` if present (none are shipped).

2. Global policy (`/app/gateway/policies/global.json`)
- Object fields: `schema_version` (number), `default_decision` (string: `allow` or `deny`).
- `default_decision` applies when no eligible route rule wins for a request.

3. Incident policy (`/app/gateway/policies/incident.json`)
- Fields: `active` (bool), `locked_hosts` (array of host strings), `break_glass_token` (string).
- Matching uses case-insensitive host comparison for `locked_hosts`.
- Header name for break-glass is exactly `X-Break-Glass` in the spec, but request header names are compared case-insensitively. The break-glass value must equal `break_glass_token` with exact string equality after trimming ASCII spaces from the header value.

4. Groups (`/app/gateway/groups/groups.json`)
- Top-level object with key `groups` mapping group name -> object with:
  - `extends`: array of group names (possibly empty), applied left-to-right as outer-to-inner layers.
  - `required_headers`: object mapping header-name string to requirement string.
- Header requirement is either a literal value (exact match, case-sensitive on the value) or `prefix:` followed by ASCII text; in the prefix form the request header value must start with that suffix text.
- Header names are matched case-insensitively against request headers.

5. Group linearization (Twist 1)
- For each group G, compute `extends_linearized`: start empty, then for each name X in G.`extends` in order, append `extends_linearized(X)` excluding duplicates that already appear, then append G itself if not already present.
- If a cycle is detected during recursive expansion, mark every group on the recursion stack as `cyclic`. Cyclic groups must not appear in `group_resolution`. Emit one violation per cyclic group: code `group_cycle`, detail `group=<name>`.

6. Effective headers for a valid group (Twist 2)
- For a non-cyclic group G with linearized list L = [g1,...,gk], merge `required_headers` in order g1..gk, then merge G’s own `required_headers` last (later keys override earlier keys).

7. Route packs (`/app/gateway/routes/*.json`)
- Each file is an object: `pack_id` (string), `rules` (array).
- Each rule object fields:
  - `id` (string), `host` (string), `host_type` (`exact`, `suffix`, `any`),
  - `path_prefix` (string, ASCII, no trailing slash unless root `/`),
  - `methods` (non-empty array of HTTP method strings or the literal `*` as a single-element array meaning any method),
  - `group` (string, optional; if missing, treat as no group),
  - `decision` (`allow` or `deny`).

8. Host matching (Twist 3)
- `exact`: request `host` equals rule `host` ASCII case-insensitively.
- `suffix`: rule `host` must begin with `*.`; let `base` be the substring after `*`. The request host matches if it is not equal to `base` and ends with `.`+`base` ASCII case-insensitively.
- `any`: always matches.

9. Method matching
- If `methods` is `["*"]`, any method matches.
- Otherwise request method must be listed with exact case-sensitive equality.

10. Route rule validation and per-request winner selection
- Global validation (single pass over every rule in every successfully read route pack, before any request is evaluated):
  - Global duplicate rule `id` strings across all packs: emit `duplicate_rule_id` violation with detail `id=<id>` once per duplicated id, and exclude every rule carrying any duplicated id from consideration for every request.
  - For each rule that declares a non-empty `group` name after trimming ASCII spaces: if that name is not a key in `groups.json`, emit `unknown_group` with detail `pack=<pack_id> rule=<id> group=<name>` and exclude that rule from consideration for every request (even when no sample request would ever match that rule’s host, path, or method). If the name is present but marked cyclic per section 5, emit `rule_uses_cyclic_group` with the same detail shape and exclude that rule from consideration for every request.
- Per-request winner selection (only rules not excluded by global validation participate):
  - A rule is path-eligible for a given request if the request path begins with the rule `path_prefix` using byte-wise ASCII prefix rules.
  - Among path-eligible rules that also match host and method, keep those that declare no group or declare a group that exists, is non-cyclic, and passes the effective header requirements from section 6 for that request’s headers. Rules excluded earlier as unknown-group or cyclic-group references never appear here.
  - Pick the winning rule by: (1) longest `path_prefix` length wins; (2) tie-break smaller `id` lexicographically; (3) tie-break smaller `pack_id` lexicographically.
  - If no winner, apply `default_decision` with reason `default`.

11. Incident override (Twist 4, cross-cutting)
- After parsing incident policy, for each request, if `active` is true and host is in `locked_hosts`:
  - If break-glass header is present and valid per section 3, skip incident enforcement for that request, add an `overrides` entry `kind`=`break_glass_skip`, and continue with normal route evaluation.
  - Otherwise decision is `deny`, reason `incident_lock`, `matched_rule_id` null, `matched_pack_id` null, `path_prefix_matched` null, `headers_required_met` false, and add `overrides` entry `kind`=`incident_lock`.

12. Output JSON (exactly five top-level keys)
Keys: `evaluations`, `violations`, `group_resolution`, `overrides`, `summary`.

`evaluations` is a JSON array sorted by `request_id` ascending. Each item:
- `request_id` (string), `decision` (`allow`|`deny`), `reason` (`matched`|`default`|`incident_lock`),
- `matched_rule_id` (string or null), `matched_pack_id` (string or null),
- `path_prefix_matched` (string or null), `headers_required_met` (bool).

`violations` is sorted by `code` ascending, then `detail` ascending. Each item: `code`, `detail`.

`group_resolution` is an object map group name -> object with keys `extends_linearized` (JSON array of strings) and `required_headers` (object). Include only groups that are defined and non-cyclic. Sort map keys lexicographically. Inside each value, `extends_linearized` preserves computed order; `required_headers` keys are sorted lexicographically.

`overrides` is sorted by `request_id` ascending, then `kind` ascending. Each item: `request_id`, `kind` (`incident_lock`|`break_glass_skip`).

`summary` keys exactly: `requests_total`, `allow`, `deny`, `incident_lock_denies`, `break_glass_rescues`, `violations_count`, `distinct_packs`. Values are non-negative integers with `requests_total` = evaluations length, `violations_count` = violations length, `distinct_packs` = number of unique `pack_id` values successfully read from route files.

13. Canonical serialization
- Serialize with two ASCII spaces per indent level, `:` separator immediately followed by a single space in pretty output lines, object keys sorted lexicographically at every object, arrays preserve order defined herein, and the file must not end with a newline.
