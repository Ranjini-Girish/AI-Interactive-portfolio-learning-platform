Normative contract for the DNS alias chain audit. Inputs are UTF-8 JSON with ASCII-only strings. Outputs are UTF-8 JSON, ASCII-only, two-space indentation, recursively sorted object keys at every depth, no trailing spaces at line ends, and exactly one trailing newline after each root closing brace.

Read `policy.json` for integer `max_chain` (positive), integer `warmup_queries`, and float `vote_ratio` between zero and one inclusive. Read `manifest.json` for `zone_tag` and `run_tag`. When they differ, set effective max chain to `max(1, max_chain // 2)` using integer floor division; record that value as `effective_max_chain` in summary. Read `epochs.json` for integer `current_epoch`. Read `queries.json` for array `queries` with integer `step`, string `name`, and string `qtype` in `A`, `AAAA`, `CNAME`, or `MX`.

Enumerate every `*.json` under `records/`. Each record has string `name`, integer `epoch`, integer `ttl_step`, optional string `alias_target`, and boolean `deny`. A record is stale when `epoch` is strictly less than `current_epoch - 1`. Packaging under `anchors/`, `meta/`, `grid/`, and `ancillary/` is ignored.

Process queries in ascending `step`, then ascending `name`. For each query, walk alias targets starting at `name`, stopping when there is no `alias_target`, when `deny` is true on the current record, when `ttl_step` is strictly less than the query `step`, when the next target was already visited (mark `looped` true), or when chain length would exceed `effective_max_chain`.

When `step` is less than or equal to `warmup_queries`, or the name is stale, or `looped` is true, or `deny_blocked` is true during the walk, `collapsed` is false. Otherwise `collapsed` is true when resolved depth is strictly greater than one and the name is not stale and not looped.

Type vote at a step: `agree_count` counts active queries on the same `step` sharing the same `qtype`. The vote is `accepted` when the name is active and `agree_count >= vote_ratio * len(queries on that step)`.

Emit `record_states.json` with `records` sorted by `name` (deny, epoch, name, stale). Emit `chain_plan.json` with `entries` in processing order for non-stale non-looped names only (chain, collapsed, depth, name, step). Emit `type_votes.json` with `votes` in processing order. Emit `query_stats.json` with `stats` in processing order (depth, deny_blocked, looped, name, step). Emit `summary.json` with collapsed_total, current_epoch, deny_blocked_total, effective_max_chain, loop_total, query_total, stale_skipped_total, vote_accepted_total.

Read `DAC_DATA_DIR` defaulting to `/app/dnschain` and `DAC_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
