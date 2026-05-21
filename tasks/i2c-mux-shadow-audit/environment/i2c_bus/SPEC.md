# I2C mux shadow audit contract

All inputs live under `/app/i2c_bus/`. Write exactly five UTF-8 JSON files under `/app/audit/` using two-space indentation, lexicographically sorted object keys at every depth, ASCII-only text, and exactly one trailing newline on each file.

## Inputs

`clock.tsv` has one row `current_day|<int>`. `policy.tsv` rows are `tier|hold_ms_floor|stretch_cap_ms` for tiers `bronze`, `silver`, and `gold`. `nodes.tsv` rows are `node_id|tier|addr7|mux_segment|serial|parent` where `parent` is `-` for roots and otherwise references an existing `node_id`. `incidents.tsv` rows are `event_id|day|kind|target|value_a|value_b|accepted` with `accepted` as `true` or `false`. The directory `probes/` holds zero or more probe files named `pNN.tsv` with rows `node_id|sample_ms`.

## Incident acceptance

Supported kinds are `hub_compromise`, `mux_freeze`, `clock_stretch`, and `nak_burst`. A row is accepted only when `accepted` is `true`, `day` is less than or equal to `current_day`, the kind is supported, and the target passes kind-specific validation. `hub_compromise`, `clock_stretch`, and `nak_burst` require `target` to equal a known `node_id`. `mux_freeze` requires `target` to equal the `mux_segment` field of at least one node. Rows that fail any check are ignored and counted in `summary.ignored_incident_events`. When multiple accepted rows share the same `kind` and `target`, keep the row with the greatest `day`, breaking ties by ascending `event_id`. All other accepted duplicates are ignored and also increment `summary.ignored_incident_events`.

## Tree and derived sets

Build a rooted forest from `parent`. The descendants of a node include all transitive children. The winning `hub_compromise` incidents define a quarantine set containing each targeted node plus every descendant. Winning `mux_freeze` incidents define a frozen set of mux segment strings taken from their `target` values. Winning `nak_burst` incidents mark their target nodes as degraded unless the node is quarantined. Winning `clock_stretch` incidents add `value_a` milliseconds to every node in the subtree rooted at `target`, including the target; each node's applied stretch is the sum of all such contributions that apply to it, then clamped by `stretch_cap_ms` of that node's tier from `policy.tsv`.

## Collisions

Ignore quarantined nodes when forming collision groups. Group remaining nodes by the pair `(addr7 as integer, mux_segment string)`. Within a group with two or more members, choose a single winner using higher tier precedence (`gold` over `silver` over `bronze`), breaking ties by smaller `serial`, then by ascending `node_id`. Every non-winner in that group becomes a collision loser. Nodes that are alone in their group are not collision losers.

## Status precedence

Each node receives exactly one status string using the first matching rule in this order: `quarantined` if the node is in the quarantine set; else `frozen` if its `mux_segment` is in the frozen set; else `shadowed` if it is a collision loser; else `degraded` if marked by a winning `nak_burst`; else `active`.

## Probes and timing

For each node, `probe_peak_ms` is the maximum `sample_ms` observed for that `node_id` across every probe file; use zero when no samples exist. Let `hold_ms` equal `hold_ms_floor` from the node's tier plus the clamped stretch sum for that node. Define `merged_budget_ms` as `hold_ms + probe_peak_ms`.

## Outputs

`node_status.json` is `{"nodes":[...]}` sorted by ascending `node_id`. Each object has `addr7`, `merged_budget_ms`, `mux_segment`, `node_id`, `reasons`, `serial`, `status`, and `tier`. `reasons` lists human-readable tokens in ascending lexicographic order chosen from this fixed menu: include `collision_loser` when status is `shadowed`; include `mux_frozen` when status is `frozen`; include `nak_degraded` when `nak_burst` applies and status is `degraded`; include `quarantine` when status is `quarantined`; include `stretch_clamped` when the pre-clamp stretch sum exceeds the tier `stretch_cap_ms`; include `nominal` when no other token applies.

`collision_edges.json` is `{"edges":[...]}` sorted by ascending `addr7`, then `loser`, then `mux_segment`, then `winner`. Each object has `addr7`, `loser`, `mux_segment`, and `winner`.

`segment_ledger.json` is `{"segments":[...]}` sorted by ascending `segment`. Each object has `segment`, `frozen` as a boolean, and `stretch_sum_ms` computed as the sum of `value_a` for every winning `clock_stretch` whose target node's `mux_segment` equals `segment`.

`timing_merge.json` is `{"nodes":[...]}` sorted by ascending `node_id`. Each object has `hold_ms`, `merged_budget_ms`, `node_id`, `probe_peak_ms`, and `stretch_effective_ms` where `stretch_effective_ms` is the clamped stretch value added into `hold_ms`.

`summary.json` contains `collision_edge_count` as the number of edges emitted, `frozen_segments` as the count of ledger rows with `frozen` true, `ignored_incident_events`, `nodes_by_status` counting every node by its final status, and `quarantined_nodes` as the number of quarantined nodes.
