# Human-in-the-loop labeling audit

All inputs live under `/app/hitl/` and are read-only. Emit five UTF-8 JSON files under `/app/audit/` using `json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False)` followed by exactly one trailing newline. Every object at every depth must have keys sorted lexicographically. Every list’s sort order is defined below; never sort keys inside list entries unless the entry itself is an object (then sort that object’s keys).

## Shared vocabulary

- **Tiers** appear on annotators: `gold`, `silver`, `bronze`.
- **Abstain** is the literal vote string `ABSTAIN` from `policy.json` field `abstain_token`.
- **Calibration gold** items have `is_calibration_gold=true` and a `gold_label` string. All other items are **open** items.

## policy.json

Fields: `abstain_token`, `min_distinct_labelers` (int), `min_winner_weight` (int), `tier_weight` (map tier→positive int).

## pool_state.json

Fields: `audit_version` (string), `current_day` (int).

## annotators/*.json

Each file contains `annotator_id` and `tier`.

## batches/*.json

Each file contains `batch_id` (string) and `business_tier` (int; smaller is higher priority).

## items/*.json

Each file contains `item_id`, `batch_id`, `is_calibration_gold`, `gold_label`, and `votes` (list of `{annotator_id, day, label}`). Labels are either non-empty strings or exactly the abstain token.

## incident_log.json

Array `incidents` of objects with `kind`, `accepted` (bool), `day` (int), `event_id` (string), and kind-specific fields.

**Accepted filter:** an incident is **active** when `accepted` is true, `day <= current_day` from `pool_state.json`, and `kind` is one of the three supported kinds below. Ignore all other incidents for logic (but count them in `summary.json` as described there).

Supported kinds:

1. `weight_scaler` — fields `annotator_id`, `effective_day`, `pct_num`, `pct_den` (positive ints). Applies to any vote cast on a day `>= effective_day` by that annotator. When multiple active scalers apply to the same annotator, compose in ascending order of `(incident.day, event_id)`.

2. `quorum_bump` — fields `batch_ids` (non-empty list of strings) and `extra_distinct` (non-negative int). For open items whose `batch_id` is listed, increase the required distinct non-abstain voter count by `extra_distinct` beyond `policy.min_distinct_labelers`.

3. `batch_freeze` — fields `batch_id`, `thaw_day` (int). While `current_day < thaw_day`, every item (gold or open) in that batch has status `blocked_freeze` and `final_label=null`, `winner_weight=0`, `runner_up_label=null`, `distinct_voters=0`, `required_distinct=0`.

## Vote weight (open items only)

For a vote with non-abstain `label` on an open item:

1. Start `w = policy.tier_weight[annotator.tier]`.
2. For each active `weight_scaler` targeting that annotator where `vote.day >= effective_day`, set `w = w * pct_num // pct_den` (integer floor at each step).
3. If the annotator has **any** calibration gold item anywhere in `/app/hitl/items/` where they cast a non-abstain vote with `label != gold_label`, set `w = w // 2` once for that annotator (after step 2).
4. If `w` is `0`, treat it as `1` for non-abstain votes.

Abstain votes contribute `0` to label sums and do not count toward distinct voters.

## Open item resolution (non-frozen batches)

Let `required_distinct = policy.min_distinct_labelers + extra_bump(batch_id)` where `extra_bump` is the sum of `extra_distinct` from every active `quorum_bump` whose `batch_ids` contains the item’s `batch_id`.

Let `V` be votes with non-abstain labels. `distinct_voters = |unique annotator_id in V|`.

- If `distinct_voters < required_distinct`: `status=insufficient_quorum`, `final_label=null`, `winner_weight=0`, `runner_up_label=null`.
- Else compute per-label sums of `w`. Let `winner` be the label with maximum sum; ties → ASCII smallest label among tied. Let `runner` be the second-highest distinct sum (if none, `null`). If `winner_sum < policy.min_winner_weight`: `status=low_confidence` but still set `final_label=winner`, `winner_weight=winner_sum`, `runner_up_label=runner`. Otherwise `status=resolved` with the same fields.

## Gold items

If `is_calibration_gold` is true and the batch is not frozen: `status=gold_locked`, `final_label=gold_label`, `winner_weight=0`, `runner_up_label=null`, `distinct_voters` equals count of unique annotators with any vote (abstain counts here), `required_distinct=0`. Gold items ignore quorum and weight thresholds.

## consensus_report.json

Top-level key `items` only. Each entry: `item_id`, `batch_id`, `status`, `final_label`, `winner_weight`, `runner_up_label`, `distinct_voters`, `required_distinct`. Sort `items` by `item_id` ascending.

## queue_order.json

Top-level key `backlog` only. Eligible items are those whose `status` is one of `{resolved, low_confidence, gold_locked}` **and** whose batch is not frozen. For each eligible item compute `eligible_day` as the minimum `day` across all of that item’s votes (abstain votes count toward the minimum).

Sort backlog by `(eligible_day asc, business_tier asc, batch_id asc, item_id asc)`, then assign `rank` starting at `1`. Each entry: `rank`, `item_id`, `batch_id`, `business_tier`, `eligible_day`.

## annotator_reliability.json

Top-level key `annotators` only. For every annotator file, emit `annotator_id`, `tier`, `gold_disagreements` (count of gold items where they voted non-abstain and `label != gold_label`), `weight_halved` (bool, true iff step 3 halving applied), `active_scalers` as the list of `{event_id, pct_num, pct_den}` for active `weight_scaler` incidents targeting them with `effective_day <= current_day`, sorted by `(day, event_id)`. If none, empty list.

Sort `annotators` by `annotator_id`.

## compliance_flags.json

Top-level key `flags` only. Include one flag per item with `status=blocked_freeze`: `{code:"freeze_active", item_id, detail:"batch=<batch_id>"}`. Include one per `status=insufficient_quorum`: `{code:"quorum_shortfall", item_id, detail:"need>=<required_distinct>"}`. Sort flags by `(code, item_id)`.

## summary.json

Keys exactly: `audit_version`, `blocked_batches`, `by_status`, `current_day`, `ignored_incidents`, `totals`.

- `by_status`: map every status string that appears in `consensus_report.items` to its count; sort keys ASCII ascending in output.
- `totals`: object with `items_total` (int), `open_items` (int), `gold_items` (int), `active_incidents` (int count of active supported incidents).
- `blocked_batches`: sorted list of `batch_id` strings that are frozen at `current_day` per `batch_freeze`.
- `ignored_incidents`: count of incidents in the log that are not active (unsupported kind, `accepted=false`, or `day > current_day`).
