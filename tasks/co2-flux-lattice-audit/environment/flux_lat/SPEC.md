# Flux lattice audit

All rules use integer arithmetic. On-disk JSON must be UTF-8 with sorted object keys, two-space indent, ASCII-only text, and a trailing newline after the closing brace.

## Inputs

Read `/app/flux_lat/policy.json` for integer `horizon_day`, map `tier_mult`, map `tier_cap`, and integer `freeze_floor`. Read `/app/flux_lat/pool_state.json` for integer map `bonus` keyed by tier. Read `/app/flux_lat/incidents.json` for array `incidents` where each row has string `id`, string `kind`, integer `day`, string `target`, and boolean `accepted`. Read every `/app/flux_lat/nodes/*.json` file; each node has string `id`, nullable string `parent`, string `tier` among `bronze`, `silver`, `gold`, integer `base`, boolean `shield`, and string `cell` referencing a cell id. Read `/app/flux_lat/cells/<id>.json` for integer `prior` used only by the node whose `cell` matches that file's `id`.

Effective caps are `effective_cap[tier] = tier_cap[tier] + bonus[tier]` using zero when a bonus key is absent.

## Incident semantics

Process incidents in ascending `day`, then ascending `id`. Only rows with `accepted == true` and `day <= horizon_day` apply.

Kinds:

- `anchor_ok` marks the target id as anchored. Anchored ids ignore compromise stamps from both direct compromise events and downstream propagation. Anchored ids still accept freeze overrides.
- `compromise` seeds propagation: if the target is anchored, ignore that compromise entirely. Otherwise stamp the target, then walk descendants following `parent` edges. Children lists are built from all nodes; traverse children in ascending child id order recursively. If a node has `shield == true`, do not stamp that node and do not enter its subtree.
- `freeze` marks the target id for freeze handling after raw scores are known.

## Scoring

For each node in ascending id order, let `prior` be the integer from its cell file.

If the node is compromise-stamped, `raw_score = 0`. Otherwise `raw_score = min((base + prior) * tier_mult[tier], effective_cap[tier])`.

If the node has an accepted freeze mark, `final_score = min(raw_score, freeze_floor)`; else `final_score = raw_score`.

## Outputs under `/app/audit`

Write `ledger.json` with object key `nodes` holding an array of rows sorted by descending `final_score`, then ascending `id`. Each row lists `id`, `tier`, integer `raw_score`, integer `final_score`, and booleans `compromised`, `anchored`, `frozen`.

Write `summary.json` with integers `total_nodes`, `stamped`, `anchored_live`, `frozen_live`, `sum_final_scores` where `sum_final_scores` is the sum of every `final_score`, and string `max_id` selecting the id with largest `final_score` using ascending id as tie-break.

Canonical emission matches `json.dumps(..., sort_keys=True, indent=2, separators=(",", ": "))` plus a trailing newline.
