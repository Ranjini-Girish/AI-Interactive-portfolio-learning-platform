# Lineage manifest audit

All JSON written by the audit uses UTF-8, two-space indent, ASCII-only text, object keys sorted lexicographically, and a single trailing newline after the closing value.

## Input layout

- `policy.json` defines `tier_rank` (map tier name to integer rank), `retention_min_tier` (map each `retention_class` value to the minimum allowed `signing_tier` name), and nothing else is normative in that file.
- `pool_state.json` carries integer `current_day` (inclusive upper bound for incidents).
- `incident_log.json` has an `events` array. Each event has string `event_id`, integer `day`, boolean `accepted`, string `kind`, and optional payloads described below. Ignore unknown fields without error.
- Every `manifests/*.json` file (non-recursive; only this directory) describes one manifest with string `manifest_id`, optional `declared_parent` (either JSON `null` or a string manifest id), string `content_digest`, string `signing_tier`, and string `retention_class`. Each `manifest_id` appears in at most one file.

## Incident kinds

Only consider events with `accepted == true` and `day <= pool_state.current_day`.

- `manifest_quarantine`: requires array `manifest_ids` of strings. Each id is quarantined for the whole audit.
- `lineage_depth_cap`: requires integer `max_depth` >= 0. When several such events apply, take the **minimum** `max_depth` across all accepted cap events that pass the day filter. If no cap events apply, there is no cap and `depth_cap_value` in `policy_screen.json` is JSON `null`.

## Quarantine and effective parents

Let `Q` be the set of quarantined manifest ids from quarantine incidents.

For manifest `m`:

1. If `m in Q`, its **effective parent** is JSON `null` (quarantined manifests act as lineage roots for themselves).
2. Otherwise if `declared_parent` is missing, JSON `null`, or equal to `m`, treat **effective parent** as JSON `null`.
3. Otherwise if `declared_parent` is not a manifest id present in the catalog, **effective parent** is JSON `null` and the child manifest id is appended to `integrity_report.missing_parent` (sorted, deduplicated).
4. Otherwise if `declared_parent in Q`, **effective parent** is JSON `null` (the upward edge stops at a quarantined ancestor without traversing through it).
5. Otherwise **effective parent** is the declared string.

## Digest rule

A manifest is listed in `integrity_report.digest_invalid` (sorted) when `content_digest` does not match `^[0-9a-f]{64}$`.

## Tier screen

For each manifest not in `digest_invalid`, compare `signing_tier` rank against the rank of `retention_min_tier[retention_class]`. If absent, treat as rank -1. A **tier violation** exists when the manifest's tier rank is strictly less than the required minimum rank. Emit objects sorted by `manifest_id` ascending with fields `manifest_id`, `required_min_tier`, `signing_tier`.

## Graph, cycles, depths

Build a directed graph on catalog manifest ids using edges `child -> effective_parent` only when effective parent is non-null.

Compute strongly connected components on this graph. A manifest is `in_cycle` when it belongs to an SCC with at least two distinct ids, or when following effective parents from that manifest would reach such an SCC without first reaching a null parent (every upstream tail that drains into a cycle counts). **SCC listing**: emit one sorted id list per SCC that has at least two vertices, listing only the ids inside that SCC (upstream tails are omitted here even though they are flagged `in_cycle` in `manifest_graph.json`). Sort the outer list of cycles by the lexicographically smallest id in each cycle, ascending.

For manifests with `in_cycle == true`, set `raw_lineage_depth` and `lineage_depth` to `-1` and `depth_cap_hit` to `false`.

For acyclic manifests, `raw_lineage_depth` is the number of hops along effective edges until reaching null. The root has `0`.

Let `cap` be the minimum cap value when any cap applies; otherwise no cap. `lineage_depth` is `raw_lineage_depth` when no cap applies. When a cap applies, `lineage_depth = min(raw_lineage_depth, cap)` and `depth_cap_hit` is `true` exactly when `raw_lineage_depth > cap`.

## Output files under the audit directory

Write exactly these five files:

1. `manifest_graph.json` with keys `nodes` then `scc_lists`. `nodes` is an array of objects sorted by `manifest_id` ascending. Each node object has keys in this order: `declared_parent` (JSON null or string as read after duplicate-file resolution), `depth_cap_hit` (boolean), `in_cycle` (boolean), `lineage_depth` (integer), `manifest_id` (string), `raw_lineage_depth` (integer), `resolved_parent` (JSON null or string—the effective parent value, using JSON `null` for absent). `scc_lists` is an array of arrays as described above.
2. `integrity_report.json` with keys `digest_invalid` then `missing_parent`, each an array of strings sorted ascending, deduplicated.
3. `policy_screen.json` with keys `depth_cap_value` (integer or null), `quarantined` (sorted ids), `tier_violations` (array as above).
4. `incident_journal.json` with key `applied_events`: every accepted event with `day <= current_day`, sorted by ascending `day` then ascending `event_id`. Each element includes `day`, `event_id`, `kind` only.
5. `summary.json` with integer counts: `cycles_detected` (number of inner arrays in `scc_lists`), `digest_invalid`, `manifests_in_catalog`, `missing_parent`, `nodes_in_cycle` (count of nodes with `in_cycle` true), `quarantined_manifests`, `tier_violation_count`.
