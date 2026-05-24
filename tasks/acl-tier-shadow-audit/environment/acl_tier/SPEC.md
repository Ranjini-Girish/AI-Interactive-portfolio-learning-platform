# ACL tier shadow audit

Normative inputs live alongside this file. All JSON is UTF-8. On-disk audit artifacts must be canonical JSON: `json.dumps(obj, sort_keys=True, indent=2, separators=(",", ": "))` plus a single trailing newline. No BOM.

## Topic patterns

Patterns use `/` segments. A literal segment matches only itself. `+` matches exactly one arbitrary segment. `#` is valid only as the final segment and matches zero or more trailing segments (including zero). Invalid patterns never appear in fixtures.

`matches(pattern, topic)` is true iff the wildcard rules above accept `topic`.

## Policy objects

`policy.json` fields:

- `cascade_tiers` — non-empty array of tier names in application order. Tiers are applied left-to-right. Each later tier may replace earlier decisions for the same client and pattern string.
- `probes` — array of objects `{ "client_id": string, "topic": string }` to evaluate after all merges and incidents.

`pool_state.json` contains integer `current_day`.

## Per-client seeds and layers

Each file under `clients/` is one object:

- `client_id` (string)
- `shadow_parent` (string or null). Null means no parent. The graph is a forest of rooted trees without cycles. Parents always appear earlier in ASCII sort order of `client_id` than all of their descendants (topological convenience only; your implementation must still follow edges).

- `seed_rules` — array of `{ "pattern": string, "action": string }` where `action` is `allow` or `deny`. Seeds are applied before any tier file, in array order, for that client only.

Each `layers/<tier>.json` where `<tier>` is a name listed in `cascade_tiers` is an object:

- `tier` — repeats the filename tier for redundancy; must equal the directory tier segment.
- `additions` — array of `{ "client_id", "pattern", "action" }` applied in array order for that tier pass only.

## Tier cascade on a single client (owned rules)

For a fixed `client_id`, build `owned` as an ordered list of rules after these steps:

1. Start with an empty ordered list and `seq = 0`.
2. Append every seed rule in file order. Each append increments `seq` by one and assigns `rule_seq = seq`, `tier_origin = null`, `introducer = client_id`.
3. For each tier name `T` in `cascade_tiers` in array order, read `layers/T.json` and scan its `additions` in array order. For each addition whose `client_id` matches, append a new rule (increment `seq`, assign `rule_seq`, set `tier_origin = T`, `introducer` to the addition's `client_id`). If the new rule's `pattern` string is byte-identical to a pattern already present for this client inside `owned`, remove the older list entry before appending so pattern strings stay unique in `owned`. Removal does not reuse old `rule_seq` numbers; the new rule always receives the freshly incremented `seq`.

## Shadow merge along the chain

Let the shadow chain for `client_id` be the list `[root, ..., client_id]` walking `shadow_parent` pointers upward to the root, then reversing to root-first order.

Let `M` be an empty map from pattern string to rule object.

For each node `U` in that root-first chain, take `owned(U)` computed by the previous section and, in `owned` list order, upsert each rule into `M` by pattern string (later upserts win). Each stored rule carries its original `rule_seq`, `tier_origin`, `introducer`, and `action` fields from the winning upsert.

The client's `effective_rules` array is all values from `M` sorted by ascending `rule_seq`, then ascending `pattern` when `rule_seq` ties.

## Incidents

`incident_log.json` contains `events`, an array of objects each having at least `event_id`, `day`, `accepted` (boolean), and `kind` (string).

An event is **eligible** when `accepted` is true, `day <= pool_state.current_day`, and its `kind` is one of the supported kinds below. Otherwise it is **ignored** for all behavioral effects. A true `accepted` value with an in-window `day` but an unsupported `kind` is ignored the same way as a false `accepted` flag.

Supported kinds:

1. `quarantine_subtree` — requires `target_client` string. Marks `target_client` and every descendant reachable via `shadow_parent` edges pointing toward children as **quarantined**. Quarantined clients emit an empty `effective_rules` array regardless of earlier merge results. Descendant discovery walks the forest downward from `target_client`.

2. `tier_strip` — requires `tier` string equal to one of `cascade_tiers` and `strip_introducer` string naming a `client_id`. After shadow merge for every client, delete any effective rule where `tier_origin == tier` **and** `introducer == strip_introducer`. Deletions happen before quarantine effects are evaluated.

Incident **application order**: sort eligible events by ascending `(day, event_id)` and apply in that order. `tier_strip` mutations apply immediately when the event is processed. `quarantine_subtree` sets quarantine flags when processed; once set, later events do not un-quarantine.

If multiple `quarantine_subtree` events target overlapping sets, the union of quarantined ids is used.

## Probes

For each probe object, if `client_id` is unknown, treat as `deny` with `reason`=`unknown_client`. If the client is quarantined, emit `deny` with `reason`=`quarantined` and null `matched_pattern` and null `matched_rule_seq`.

Otherwise scan all effective rules for that client in descending `rule_seq` order and collect every rule whose `pattern` matches the probe `topic`. If none match, emit `deny` with `reason`=`default_deny` and null `matched_pattern`, null `matched_rule_seq`.

If one or more match, pick the single rule with the largest `rule_seq`. Emit that rule's `action` (`allow` or `deny`) as `decision`, copy its `pattern` to `matched_pattern`, copy `rule_seq` to `matched_rule_seq`, and set `reason`=`matched`.

## Outputs (under audit directory)

Write three files:

### `effective_access.json`

Top-level keys fixed as:

- `clients` — array sorted by ascending `client_id`. Each element: `{ "client_id", "quarantined" (boolean), "rules" }`.
- `rules` — array sorted ascending by `rule_seq` then `pattern`. Each rule: `{ "pattern", "action", "rule_seq", "tier_origin" (null or string), "introducer" }`.

### `probe_verdicts.json`

- `probes` — array in the same order as `policy.probes`. Each element: `{ "client_id", "topic", "decision", "reason", "matched_pattern", "matched_rule_seq" }` where `matched_pattern` and `matched_rule_seq` may be JSON null.

### `summary.json`

Keys:

- `clients_total` — count of all `clients/*.json` files.
- `quarantined_clients` — sorted list of distinct quarantined ids.
- `probes_total` — length of `policy.probes`.
- `allow_probe_count` — probes whose `decision` is `allow`.
- `deny_probe_count` — probes whose `decision` is `deny`.
- `applied_incidents` — sorted list of `event_id` strings that were eligible and affected state (quarantine sets or tier_strip deletions). `tier_strip` always counts as applied when eligible even if it deletes zero rows.
- `ignored_incidents` — count of events not eligible.

## Anchors

Files under `anchors/` are opaque bytes for packaging density only; the audit ignores them.
