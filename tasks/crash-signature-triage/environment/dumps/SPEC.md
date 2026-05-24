# Crash Signature Triage — Output Contract

This file is part of the read-only input dataset under `/app/dumps/`. It defines exactly how the five output JSON files at `/app/triage/` must be derived from the inputs. Every requirement here is binding.

## Inputs

The dataset under `/app/dumps/` contains:

- `pool_state.json` — `{"current_day": <int>=0>, "triage_version": "<str>"}`. `current_day` is the triage reference day; every `day` field elsewhere is a non-negative integer.
- `triage_config.json` — `{"cluster_size_escalation_threshold": <int>=2>, "default_owner_team": "<str>", "severity_order": ["low", "medium", "high", "critical"]}`. `severity_order` is fixed; it is reproduced in the spec for clarity.
- `module_map.json` — `{"modules": [{"frame_prefix": "<str>", "owner_team": "<str>"}]}`. Each `frame_prefix` is the prefix of a frame string (e.g., `"render::"`). Two modules with the same `frame_prefix` are an authoring error; if present, the last entry wins.
- `incident_log.json` — `{"events": [...]}` (filtering rules below).
- `releases/<version>.json` — `{"version": "<str>", "day": <int>=0>, "diff_hash": "<64 lowercase hex>", "owner_team": "<str>"}`. The set of releases is exactly the files in `releases/`.
- `crashes/<id>.json` — `{"id": "<str>", "reported_day": <int>=0>, "reporter": "<str>", "frame_stack": ["<frame>", ...], "env_hash": "<64 lowercase hex>", "reproducibility": "always"|"intermittent"|"once", "severity_observed": "low"|"medium"|"high"|"critical"}`. The set of crashes is exactly the files in `crashes/`.

## Validation and silent-drop rules

A record is **valid** iff every field matches its documented type and range. Specifically:

- A crash is valid iff `id` is a non-empty string, `reported_day` is in `[0, current_day]`, `reporter` is a non-empty string, `frame_stack` is a non-empty list of non-empty strings, `env_hash` matches `^[0-9a-f]{64}$`, `reproducibility` is one of the three values, and `severity_observed` is one of the four values.
- A release is valid iff `version` is a non-empty string, `day` is in `[0, current_day]`, `diff_hash` matches `^[0-9a-f]{64}$`, and `owner_team` is a non-empty string.

Every invalid record is silently dropped from all downstream computation and counted in `summary.totals.invalid_<entity>_dropped`.

An incident event is **accepted** iff **all** hold: `kind` is one of `"poisoned_build"`, `"owner_reassign"`, `"cluster_merge"`; `day` is an integer with `0 <= day <= pool_state.current_day`; and the kind-specific fields validate:

- `poisoned_build` — `diff_hash` matches `^[0-9a-f]{64}$`; `reason` is a non-empty string.
- `owner_reassign` — `event_id` is a non-empty string; `signature` is a non-empty string that resolves to a canonical cluster signature **before** any merges are applied (see "Cluster merges" below); `new_owner_team` is a non-empty string.
- `cluster_merge` — `event_id` is a non-empty string; `source_signature` and `target_signature` are non-empty strings that both resolve to distinct canonical cluster signatures present in the initial mapping; `source_signature != target_signature`.

Every other event is silently ignored and counted in `summary.totals.ignored_incident_events`.

## Canonical cluster signature

For a valid crash with `frame_stack` of length `n`, compute the **canonical signature** as follows:

1. If `n >= 4`: combine the first three frames and the last frame in that order: `frame_stack[0:3] + [frame_stack[-1]]`.
2. If `n < 4`: take the entire `frame_stack` in its original order.
3. Walk the resulting list left-to-right and discard any frame that already appeared earlier (deduplication keeps the first occurrence).
4. Join the resulting list with a single ASCII pipe `"|"` (no surrounding whitespace) between adjacent frames. The result is the cluster `signature` (a string).

Two crashes that produce the same `signature` belong to the same cluster.

## Cluster merges

The initial cluster mapping assigns each valid crash to the cluster keyed by its canonical signature. After this initial mapping is established, accepted `cluster_merge` events are applied **in order of**: ascending `day`, ASCII-ascending `event_id` on ties. For each event:

1. If both `source_signature` and `target_signature` resolve to clusters that **currently exist** (i.e., have not already been merged away), all crashes in the `source_signature` cluster are reassigned to the `target_signature` cluster. The `source_signature` is recorded in `merged_from` of the target cluster and removed from the cluster mapping.
2. If either side does not resolve to a currently-existing cluster, the event is silently ignored and counted in `summary.totals.ignored_incident_events`.

`merged_from` of the target cluster accumulates the sorted-ascending union of every absorbed source signature across all applied merges.

## Release-window attribution

For each surviving cluster, compute `first_seen_day = min(crash.reported_day)` over its crashes (after merges). The **attributed release** is the release with the smallest `day >= first_seen_day`, with ties on `day` broken by ASCII-smallest `version`. If no such release exists, `attributed_release` is `null` and `attributed_diff_hash` is `null`.

`attribution_note` is `"release_match"` for normal attribution, `"unattributed"` when no release qualifies, and `"poisoned_build"` when the poisoned-build override (below) fires.

## Severity computation

For each surviving cluster, define the **observed severity** as the maximum of its crashes' `severity_observed` under the order in `triage_config.severity_order` (`low < medium < high < critical`). Then the cluster's `computed_severity` is determined by the **first applicable** rule:

1. `"critical"` with reason `"escalated_poisoned_build"` — the cluster is affected by an accepted `poisoned_build` event (see below).
2. `"critical"` with reason `"escalated_reproducibility_always"` — at least one crash in the cluster has `reproducibility == "always"`.
3. `"critical"` with reason `"escalated_cluster_size_<n>"` — the cluster contains at least `triage_config.cluster_size_escalation_threshold` crashes (where `<n>` is the exact crash count).
4. Otherwise, `computed_severity` equals the observed severity with reason `"max_observed_<sev>"`.

## Owner assignment

For each surviving cluster, `assigned_owner_team` and `assignment_reason` are determined by the **first applicable** rule:

1. `"release-engineering"` with reason `"poisoned_build_override"` — the cluster is affected by an accepted `poisoned_build` event.
2. The `new_owner_team` of the **latest** accepted `owner_reassign` event whose `signature` equals this cluster's post-merge signature, with reason `"owner_reassign"`. "Latest" means largest `day`, ties broken by ASCII-smallest `event_id`. An accepted `owner_reassign` whose `signature` is no longer a current cluster signature after all merges have been applied is silently re-classified as ignored and counted in `summary.totals.ignored_incident_events`.
3. The `owner_team` from `module_map.modules` whose `frame_prefix` is the **longest** prefix of the cluster signature's first frame (the substring of the joined signature up to but not including the first `"|"`, or the entire signature if it contains no `"|"`), with reason `"module_match"`. Ties on prefix length are broken by ASCII-smallest `frame_prefix`. A module entry whose `frame_prefix` is not actually a prefix of the first frame is ignored.
4. The attributed release's `owner_team` with reason `"release_default"`, if `attributed_release` is non-null.
5. `triage_config.default_owner_team` with reason `"default_owner"`.

## Poisoned-build override

A cluster is **affected by `poisoned_build`** iff its `attributed_release` is non-null **and** there is at least one accepted `poisoned_build` event whose `diff_hash` equals the attributed release's `diff_hash`. The set of affected clusters is computed once after attribution and before severity/owner classification. Affected clusters get `attribution_note = "poisoned_build"`, `computed_severity = "critical"` (rule 1 above), and `assigned_owner_team = "release-engineering"` (rule 1 above).

## Output schemas

All five outputs live under `/app/triage/` and use the canonical encoding `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)` followed by exactly one trailing newline byte. List ordering below is part of the contract; two correct implementations of this contract must produce byte-identical output for the same input. Integer-valued counts must be emitted as JSON integers (not `1.0`).

### `/app/triage/cluster_index.json`

```
{"clusters": [{"signature": "<str>", "crashes": ["<id>", ...], "first_seen_day": <int>, "last_seen_day": <int>, "merged_from": ["<str>", ...]}]}
```

`clusters` is sorted by `signature` ascending. `crashes` and `merged_from` are sorted ascending.

### `/app/triage/attribution_report.json`

```
{"clusters": [{"signature": "<str>", "attributed_release": "<str>"|null, "attributed_diff_hash": "<str>"|null, "attribution_note": "<str>"}]}
```

`clusters` is sorted by `signature` ascending.

### `/app/triage/severity_ranking.json`

```
{"clusters": [{"signature": "<str>", "observed_severity": "<str>", "computed_severity": "<str>", "severity_reason": "<str>"}]}
```

`clusters` is sorted by `signature` ascending.

### `/app/triage/owner_assignment.json`

```
{"clusters": [{"signature": "<str>", "assigned_owner_team": "<str>", "assignment_reason": "<str>"}]}
```

`clusters` is sorted by `signature` ascending.

### `/app/triage/summary.json`

```
{"current_day": <int>, "triage_version": "<str>", "totals": {"crashes": <int>, "clusters": <int>, "releases": <int>, "invalid_crashes_dropped": <int>, "invalid_releases_dropped": <int>, "ignored_incident_events": <int>, "merged_clusters": <int>}, "by_severity": {"low": <int>, "medium": <int>, "high": <int>, "critical": <int>}, "by_attribution_note": {"release_match": <int>, "unattributed": <int>, "poisoned_build": <int>}, "by_assignment_reason": {"module_match": <int>, "release_default": <int>, "owner_reassign": <int>, "poisoned_build_override": <int>, "default_owner": <int>}, "poisoned_clusters": ["<str>", ...]}
```

`totals.crashes` counts valid crashes (not dropped). `totals.clusters` counts surviving clusters after merges. `totals.merged_clusters` is the number of `cluster_merge` events that were successfully applied. `poisoned_clusters` is the sorted-ascending list of every signature whose `attribution_note` is `"poisoned_build"`. Every documented enum key in `by_severity`, `by_attribution_note`, and `by_assignment_reason` must appear with an integer value (zero if absent). Do not modify any file under `/app/dumps/` while computing the report.
