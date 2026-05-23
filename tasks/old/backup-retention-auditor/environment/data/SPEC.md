# Backup Retention Auditor — Output Contract

This file is part of the read-only input dataset under `/app/data/`. It defines exactly how the five output JSON files at `/app/audit/` must be derived from the inputs. Every requirement in this file is binding.

## Snapshot validation

A snapshot record (an entry of any `snapshots/<host>.json` file's `snapshots` list) is **valid** iff **all** of the following hold:

- `id` is a non-empty string.
- `kind` is one of the literals `"full"` or `"incremental"`.
- `taken_day` is an integer with `0 <= taken_day <= pool_state.current_day`.
- `size_mb` is a non-negative integer.
- `sha256_chain` is exactly 64 lowercase hexadecimal characters (matches `^[0-9a-f]{64}$`).
- When `kind == "incremental"`, `parent_id` is a non-empty string.

Invalid snapshots are silently dropped from every downstream computation but are counted in `summary.invalid_snapshots_per_host`.
`summary.invalid_snapshots_per_host` includes only hosts whose invalid-snapshot count is at least 1 (hosts with zero invalid snapshots are omitted).

## Incident-log filtering

An entry of `incident_log.events` is **accepted** iff **all** of the following hold:

- `kind` is one of `"tamper"`, `"restore_failure"`, or `"chain_break"`.
- `day` is an integer and `day <= pool_state.current_day`.
- `snapshot_id` matches the `id` of some valid snapshot.
- `day >= taken_day` of that referenced snapshot. An event whose `day` precedes the snapshot's `taken_day` is rejected (an incident cannot reference a snapshot that did not yet exist).

Every other incident event is silently ignored and counted in `summary.ignored_incident_events`. Accepted `restore_failure` events produce no output finding (they are tracked only as "accepted" for the purposes of the ignored count).

Every event also carries a `containment_window_days` field (an integer `>= 0`). It is only consulted for accepted `tamper` events; for events of other kinds, or for events that are ignored for any reason, it is irrelevant.

## Tamper containment (pre-retention propagation pass)

This pass runs **before** retention selection and removes contaminated snapshots from every downstream computation. It applies to all hosts, including exempt hosts.

For each accepted `tamper` event T referencing valid snapshot S with `T.containment_window_days = W`, the **containment closure of T** is the set:

- S itself, **plus**
- every valid same-host snapshot D such that D is a transitive descendant of S — that is, the chain `D, parent(D), parent(parent(D)), ...` in S's host (following only `parent_id` edges that resolve to valid same-host snapshots) reaches S — **and** `D.taken_day - S.taken_day <= W`.

The host-level **contained set** is the union of the containment closures of every accepted tamper event that references a valid snapshot of that host. A snapshot may end up contained either as the directly-tampered subject of one event, or as a descendant of any tampered subject whose own event's window admits it; the union semantics mean a single descendant taken within at least one tamper's window is contained even if a different tamper's window would have excluded it.

Contained snapshots:

- Are excluded from every retention rule's candidate set (so they cannot fill buckets, and a rule's `keep_count` slots will be filled by other eligible snapshots instead).
- Are reported in `retention.json` with `decision = "evict"`, `reason = "tamper_containment"`, `matched_rule = null`.
- Are reported in `eviction_plan.containment_evictions` (see schema below).
- Contribute their `size_mb` to `summary.total_size_contained_mb`.

Containment runs strictly before retention. It does **not** modify the `compromised` list in `integrity.json` (which still lists exactly the snapshots referenced by accepted `tamper` events, regardless of whether their descendants were contained). Containment also does not alter chain-break classification.

## Retention rules

A retention rule applies to a host iff its `applies_to_tier` equals the host's `tier` or is the literal `"*"`.

Each host's profile lives in its own file `host_profiles/<host>.json`; the union of those files (in alphabetical order of the `host` field) constitutes the `host_profiles` collection referenced below. A host whose profile has `exempt == true` keeps every valid **non-contained** snapshot regardless of any rule; the `matched_rule` for those snapshots is the literal string `"exempt"`. (Contained snapshots of an exempt host are still evicted with `reason = "tamper_containment"`.)

A host whose `override_rules` list is non-empty replaces — only for the `kind` values present in its overrides — every global rule of that same `kind`; rules of other `kind` values still come from the global `retention_policy.rules`. When the `override_rules` list contains more than one entry of the same `kind`, only the **last** such entry (highest list index) participates in the host's effective rules; earlier entries with the same `kind` are silently dropped before the global-vs-override merge. The host's **effective rules** are therefore: every global rule whose `kind` is not in the override-kind set, plus the de-duplicated (last-wins) override list.

For each non-exempt host, evaluate every applicable effective rule:

1. The rule's **candidate set** is every valid **non-contained** snapshot of this host whose age satisfies `pool_state.current_day - taken_day <= max_age_days`.
2. Group the candidate set into **buckets** by `kind`:
   - `daily`:   bucket index = `taken_day`
   - `weekly`:  bucket index = `taken_day // 7`
   - `monthly`: bucket index = `taken_day // 30`
   - `yearly`:  bucket index = `taken_day // 365`
3. Within each bucket pick the snapshot with the largest `taken_day`; break ties by ASCII-smallest `id`.
4. Order buckets by bucket index descending. The rule **selects** the first `keep_count` of those bucket-winners. (If `keep_count <= 0`, the rule selects nothing.)

A snapshot is **kept by retention** iff at least one applicable rule selects it. Its `matched_rule` is the rule with the **smallest** `priority` integer among the rules that selected it; ties on priority are broken by ASCII-smallest rule `name`. Snapshots not kept by any rule (and not contained) are evicted with `reason = "no_matching_rule"`.

## Hash-chain integrity (per host)

A valid snapshot whose `kind == "incremental"` is a **chain break** iff its `parent_id` does not equal the `id` of any valid snapshot of the same host. (No transitive walk; only the snapshot's own immediate `parent_id` is checked.) Each chain break is recorded with:

- `status = "explained_break"` when the broken snapshot's own `id` appears in an accepted incident event with `kind == "chain_break"`.
- `status = "unexpected_break"` otherwise.

A snapshot is **compromised** iff its `id` appears in an accepted incident event with `kind == "tamper"`. Compromised snapshots are added to their host's `compromised` list regardless of decision or chain status (a tamper-referenced snapshot is in `compromised` even though the same snapshot is also contained and therefore evicted).

A host's `integrity_status` is `"compromised"` if it has any compromised snapshot; otherwise `"chain_issues"` if it has any chain break (explained or unexpected); otherwise `"ok"`.

## Capacity-driven eviction (two-pass)

After retention selection (which already excludes contained snapshots), compute the size of the retained set per tier and globally. Capacity eviction proceeds in two passes; both passes operate strictly on the retained set excluding exempt-host snapshots (exempt-host snapshots are never capacity-evicted).

The eviction priority key, in this exact order, is:

1. Host `tier` ascending, where the order is `bronze < silver < gold` (numeric ranks `0 < 1 < 2`).
2. `taken_day` ascending (oldest first).
3. `size_mb` descending (largest first).
4. `id` ascending (ASCII).

**Pass 1 — tier_quota.** Iterate the three tiers in the order `bronze, gold, silver` (alphabetical by tier name). For each tier T, let `quota = pool_state.tier_quotas[T]`. If the current per-tier total (sum of `size_mb` over retained non-exempt snapshots of tier T) exceeds `quota`, repeatedly evict the highest-priority retained snapshot of tier T until the tier total fits within `quota`. The priority key above is used restricted to snapshots of tier T. Each eviction is recorded with `pass = "tier_quota"`.

**Pass 2 — global_capacity.** After Pass 1 completes, if the running global total still exceeds `pool_state.capacity_mb`, repeatedly evict the highest-priority retained non-exempt snapshot using the priority key above (now unrestricted by tier), until the global total fits within `pool_state.capacity_mb`. Each eviction is recorded with `pass = "global_capacity"`.

`eviction_plan.evictions` lists every capacity-evicted snapshot in the exact order it was evicted: Pass 1's evictions first (in tier-iteration order `bronze, gold, silver`, with priority order within each tier), then Pass 2's evictions. `running_size_mb` is the global retained total after this entry has been evicted, decreasing monotonically across the entire list. Each capacity-evicted snapshot is recorded in `retention.json` with `reason = "capacity_overflow"` and `matched_rule = null`, regardless of which pass evicted it.

## Cascading eviction (post-pass)

After both capacity-driven eviction passes complete, apply this propagation pass over each host's parent-chain graph. A snapshot S is **cascade-evicted** iff **all** of the following hold:

- S is currently kept (i.e., S was selected by retention AND was not capacity-evicted in either pass AND is not contained).
- `S.kind == "incremental"`.
- At least one of S's transitive ancestors — chained through `parent_id` within S's own host, following only valid same-host snapshots — is in the capacity-evicted set (from either pass).

Cascade-evicted snapshots are recorded in `retention.json` with `decision = "evict"`, `reason = "cascade_overflow"`, and `matched_rule = null`. They do **not** appear in `eviction_plan.evictions` or `eviction_plan.containment_evictions`. All `host_summary.kept_*` fields and `summary.total_size_after_eviction_mb` are computed strictly over snapshots whose final `decision == "keep"` and therefore exclude contained, capacity-evicted, and cascade-evicted snapshots. Exempt hosts are never affected by cascading (their snapshots are never capacity-evicted, so the trigger condition cannot apply).

A snapshot is never simultaneously contained and cascade-evicted: containment removes the snapshot from retention selection entirely, so the "S is currently kept" precondition cannot hold.

## Final decision

Every valid snapshot's `decision` is exactly one of:

- `"keep"`: not contained, kept by retention, not capacity-evicted, and not cascade-evicted. `reason` is `"retained_by_rule"` for non-exempt hosts and `"exempt"` for exempt hosts. `matched_rule` is the rule's `name` (or `"exempt"`).
- `"evict"`: contained OR not kept by retention OR capacity-evicted OR cascade-evicted. `reason` is one of `"tamper_containment"`, `"no_matching_rule"`, `"capacity_overflow"`, or `"cascade_overflow"` per the rules above. `matched_rule` is `null` for every evict reason.

## Output schemas

All five outputs are written under `/app/audit/`. List ordering is part of the contract.

### `/app/audit/retention.json`

```
{"snapshots": [{"id": "...", "host": "...", "decision": "keep"|"evict", "reason": "...", "matched_rule": "..."|null}]}
```

`snapshots` is sorted by `(host, id)` ascending. Entries have exactly the five keys above.

### `/app/audit/eviction_plan.json`

```
{
  "capacity_mb": <int>,
  "initial_size_mb": <int>,
  "final_size_mb": <int>,
  "evictions": [{"id": "...", "host": "...", "pass": "tier_quota"|"global_capacity", "size_mb": <int>, "running_size_mb": <int>}],
  "containment_evictions": [{"id": "...", "host": "...", "size_mb": <int>}]
}
```

`evictions` lists capacity-evicted snapshots only (retention-evicted, contained, and cascade-evicted snapshots do not appear here), in the exact eviction order specified in "Capacity-driven eviction (two-pass)". `running_size_mb` is the global retained total after this entry has been evicted. `initial_size_mb` is the retained-set total **after** containment and retention but **before** either capacity-eviction pass. `final_size_mb` is the retained-set total after both passes complete (still before cascade).

`containment_evictions` lists every contained snapshot, sorted by `(host, id)` ascending. Each entry has exactly the three keys `id`, `host`, `size_mb`.

### `/app/audit/integrity.json`

```
{"hosts": [{"host": "...", "chain_breaks": [{"id": "...", "parent_id": "...", "status": "explained_break"|"unexpected_break"}], "compromised": ["..."]}]}
```

`hosts` is sorted by `host` ascending; `chain_breaks` is sorted by `id` ascending; `compromised` is sorted ascending. Entries have exactly the keys above.

### `/app/audit/host_summary.json`

```
{"hosts": [{"host": "...", "tier": "...", "exempt": <bool>, "valid_snapshots": <int>, "kept_count": <int>, "evicted_count": <int>, "kept_size_mb": <int>, "oldest_kept_day": <int>|null, "integrity_status": "ok"|"chain_issues"|"compromised"}]}
```

`hosts` is sorted by `host` ascending. `oldest_kept_day` is `null` iff `kept_count == 0`, otherwise the smallest `taken_day` among that host's kept snapshots. Entries have exactly the keys above.

### `/app/audit/summary.json`

```
{
  "capacity_mb": <int>,
  "current_day": <int>,
  "total_valid_snapshots": <int>,
  "total_invalid_snapshots": <int>,
  "total_size_before_eviction_mb": <int>,
  "total_size_after_eviction_mb": <int>,
  "total_size_contained_mb": <int>,
  "ignored_incident_events": <int>,
  "invalid_snapshots_per_host": {"<host>": <int>}
}
```

`invalid_snapshots_per_host` keys are sorted ascending. `total_size_before_eviction_mb` equals `eviction_plan.initial_size_mb` (the retained-set total after containment and retention, before either capacity-eviction pass). `total_size_after_eviction_mb` equals the sum of `size_mb` over all snapshots whose final `decision == "keep"` in `retention.json` (i.e., it equals `eviction_plan.final_size_mb` when no cascade evictions occur, and is strictly less when they do). `total_size_contained_mb` equals the sum of `size_mb` over every entry in `eviction_plan.containment_evictions`.
