# Stream Shard Rebalancer — Output Contract

This file is part of the read-only input dataset under `/app/cluster/`. It defines exactly how the five output JSON files at `/app/plan/` must be derived from the inputs. Every requirement in this file is binding.

## Input layout (read-only)

- `pool_state.json` — `{ "current_day": int }`.
- `policy/rebalance_policy.json` — replication and demotion policy.
- `topology/cluster.json` — `{ "brokers": [ {broker_id, availability_zone, region, pool, nominal_capacity_mbps, utilization_overhead_pct, backpressure_threshold_pct} ] }`.
- `topology/azs.json` — `{ "azs": { az_id: region_id } }`.
- `topics/<topic_id>.json` — `{ topic_id, partitions, tier, target_lag_messages, current_throughput_mbps_per_partition, current_lag_messages: { "<partition_id>": int }, current_leader_map: { "<partition_id>": broker_id } }`. `tier ∈ {"gold","silver","bronze"}`. `partitions` is an integer; partitions are numbered `0..partitions-1`. Every `partition_id` from `0` to `partitions-1` appears as a string key in both `current_lag_messages` and `current_leader_map`. `current_throughput_mbps_per_partition` is a single positive integer applied uniformly to every partition of the topic.
- `consumers/<group_id>.json` — `{ group_id, subscription, members: [ {member_id, consumption_capacity_mbps} ] }`. `subscription` is either `"literal:<topic_id>"` or `"regex:<pattern>"` (pattern is anchored: it must fully match each candidate `topic_id`).
- `incidents/incident_log.json` — `{ "events": [ ... ] }`. Event fields documented under *Incident filtering* below.

## Incident filtering

An event is **accepted** iff all of: `accepted == true`, `day ≤ current_day`, `kind ∈ {"broker_quarantine","partition_freeze","capacity_override"}`, and the kind-specific fields below are valid. For `broker_quarantine` the event is additionally rejected when `evac_day > current_day`. All other events are silently ignored and counted in `summary.ignored_incident_events`. Accepted events apply in order of `(day asc, event_id ASCII asc)`.

- `broker_quarantine` requires `broker_id` (existing) and integer `evac_day ≤ current_day`.
- `partition_freeze` requires `topic_id` (existing) and `partition_id` (in range for that topic).
- `capacity_override` requires `broker_id` (existing) and positive integer `new_capacity_mbps`.

## Placement (Phase 1)

For every partition `(topic_id, p)`, the **eligible-broker pool** is: gold tier may draw from brokers whose `pool` is `reserved-gold` or `shared`; silver and bronze may draw only from `shared`. Brokers under an accepted `broker_quarantine` are excluded from every eligible pool.

`replication_factor` per tier: `gold=3, silver=2, bronze=1`.

For replica slot `s ∈ {0..RF-1}` of partition `(topic_id, p)`:

1. Compute `h = uint64(big_endian(sha256(topic_id + ":" + p + ":" + s)[:8]))`.
2. Sort the eligible pool by `broker_id` ASCII ascending. Set `start = h mod len(pool)`.
3. Walk forward (with wraparound) over the sorted pool, skipping brokers already chosen for this partition. Among the remaining, pick the first whose `availability_zone` differs from every previously-chosen replica's AZ. If no such broker exists in the walk, fall back to the first whose `region` differs. If neither rule can be satisfied, pick the first remaining broker and increment `summary.anti_affinity_violations_blocked` by 1.

Slot 0 is the `leader_broker`; slots 1..RF-1 are `replica_brokers` sorted ASCII ascending in the output. `placement_reason = "hash_placement"`. Any partition not overridden by the freeze rules in Phase 2 has `status = "active"`.

## Freeze override (Phase 2)

For each accepted `partition_freeze` for `(topic_id, p)`: set `leader_broker = current_leader_map[p]` (override the Phase 1 leader). Replica brokers are unchanged. If the frozen leader broker is also under an accepted `broker_quarantine`, the partition's `placement_reason = "frozen_during_quarantine"` and its `status = "frozen"`; the broker's status in `quarantine_status.json` is `frozen_quarantined` rather than `quarantined`. Otherwise `status = "frozen"` and `placement_reason = "frozen_by_event"`.

## Backpressure demotion (Phase 3)

For each broker, `effective_capacity_mbps = (nominal * (100 - utilization_overhead_pct)) / 100` using **integer floor division** (e.g. `5280 / 100 → 52`, not `52.8` or `53`). `nominal` is the `new_capacity_mbps` of an accepted `capacity_override` if present, else `nominal_capacity_mbps`. Broker `current_load_mbps` is the sum of `current_throughput_mbps_per_partition` over partitions where it is the **leader** after Phases 1–2; replicas do not contribute load. The threshold check is `100 * current_load_mbps > backpressure_threshold_pct * effective_capacity_mbps` (integer-only comparison, no float arithmetic anywhere).

Iterate brokers in ASCII order. While `100 * current_load_mbps > backpressure_threshold_pct * effective_capacity_mbps`:

- Pick the leader partition on this broker that has the lowest tier among `{bronze, silver}` (i.e. only non-gold partitions are candidates), breaking ties by ASCII-largest `topic_id` then highest `partition_id`. Frozen partitions and partitions already demoted in this phase are never candidates. If no candidate exists, stop demoting on this broker and proceed to the next broker — the broker remains over-threshold and that is acceptable (gold-only loads cannot be relieved).
- Otherwise re-run the slot-0 hash placement (Phase 1) with the current broker added to the exclusion set. Assign the partition's `leader_broker` to that result, set `placement_reason = "demoted_for_backpressure"`, increment `summary.demotions_total` by 1, and update both brokers' load counters. Continue the inner loop on the current broker.

A partition that has been demoted once is **not** eligible to be demoted again, even if its new broker is later processed and is over-threshold; this guarantees termination.

## Consumer rebalance (Phase 4)

For each consumer group, materialize its **subscribed-topic set**: every `topic_id` matched by `subscription` (literal equality or full-string regex match against the topic_id). The **eligible-partition set** is every `(topic_id, p)` whose topic is in the subscribed-topic set **excluding** any partition that is `status == "frozen"` after Phase 2 — frozen partitions are unconsumable while parked and go into `unassigned_partitions` with `reason="frozen"`.

Sort the eligible partitions by `(current_lag_messages desc, current_throughput_mbps_per_partition desc, topic_id ASCII asc, partition_id asc)`. For each partition in order, assign it to the member whose current `assigned_lag_sum` (sum of `current_lag_messages` of partitions already assigned to that member) is smallest, ties broken by ASCII-smallest `member_id`. Each member starts with `assigned_lag_sum = 0` and an empty assignment list; a member with no eligible partitions still appears in `member_assignments` with an empty list.

`projected_max_member_lag_messages` is the largest per-member `assigned_lag_sum` (or `0` when the group has zero eligible partitions). `projected_total_throughput_mbps` is the sum of `current_throughput_mbps_per_partition` over all assigned (not unassigned) partitions. Let `T = min(target_lag_messages)` over topics with at least one assigned partition (or `0` if none). `lag_status` is determined by integer-only comparison: `"within_target"` if `T == 0` or `5 * projected_max < 4 * T`; `"exceeded"` if `T > 0` and `projected_max ≥ T`; `"near_threshold"` otherwise. `exceeding_members` lists ASCII-sorted `member_id`s whose individual `assigned_lag_sum ≥ T` (empty when `T == 0`).

## Output schema

All outputs are at `/app/plan/`. Encoding rule: `json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"`, UTF-8. Every list in the output uses the sort order documented per field below.

- `partition_assignment.json` — `{"partitions": [...]}`. Each entry has fields `{leader_broker, partition_id, placement_reason, replica_brokers, status, tier, topic_id}` where `status ∈ {"active","frozen"}` and defaults to `"active"` unless changed by Phase 2. `replica_brokers` is ASCII sorted. Sorted by `(topic_id, partition_id)`.
- `consumer_rebalance.json` — `{"groups": [...]}`. Each entry has `{group_id, member_assignments, subscribed_topics, unassigned_partitions}`. `member_assignments` is an object keyed by `member_id`; each value is a list of `{partition_id, topic_id}` sorted by `(topic_id, partition_id)`. Every member of the group appears as a key even with an empty list. `subscribed_topics` is ASCII sorted. `unassigned_partitions` is a list of `{partition_id, reason, topic_id}` (with `reason = "frozen"`) sorted by `(topic_id, partition_id)`. Groups sorted by `group_id`.
- `lag_report.json` — `{"groups": [...]}`. Each entry has `{exceeding_members, group_id, lag_status, projected_max_member_lag_messages, projected_total_throughput_mbps}`. Sorted by `group_id`.
- `quarantine_status.json` — `{"brokers": [...]}`. Each entry has `{broker_id, effective_capacity_mbps, over_threshold, partitions_evacuated_count, partitions_received_count, post_rebalance_load_mbps, status}`. `post_rebalance_load_mbps` is the integer sum of `current_throughput_mbps_per_partition` over partitions where this broker is the **leader** in the final plan. `over_threshold` is the boolean `100 * post_rebalance_load_mbps > backpressure_threshold_pct * effective_capacity_mbps` evaluated on the final post-Phase-3 load. `partitions_evacuated_count` is the number of partitions whose `current_leader_map` value was this broker but whose final `leader_broker` is different. `partitions_received_count` is the number of partitions whose final `leader_broker` is this broker but whose `current_leader_map` value was not. `status ∈ {"active","quarantined","frozen_quarantined","capacity_overridden"}`; an accepted `capacity_override` produces `capacity_overridden` only when the broker is not also `quarantined` or `frozen_quarantined`. Sorted by `broker_id`.
- `summary.json` — flat object with exactly these keys: `accepted_incident_events`, `active_brokers`, `anti_affinity_violations_blocked`, `brokers_over_threshold`, `brokers_total`, `capacity_overridden_brokers`, `consumer_groups_total`, `demotions_total`, `frozen_partitions`, `frozen_quarantined_brokers`, `groups_with_lag_exceeded`, `groups_with_lag_within_target_or_near`, `ignored_incident_events`, `partitions_total`, `quarantined_brokers`, `topics_total`. All integer-valued.

Summary count definitions (normative):

- `active_brokers`: number of brokers whose final `status` in `quarantine_status.json` is exactly `"active"` (do not include `"capacity_overridden"`).
- `quarantined_brokers`: number of brokers whose final status is exactly `"quarantined"` (exclude `"frozen_quarantined"`).
- `frozen_quarantined_brokers`: number of brokers whose final status is exactly `"frozen_quarantined"`.
- `capacity_overridden_brokers`: number of brokers whose final status is exactly `"capacity_overridden"`.
- `brokers_over_threshold`: number of brokers whose final `over_threshold` is `true`.
