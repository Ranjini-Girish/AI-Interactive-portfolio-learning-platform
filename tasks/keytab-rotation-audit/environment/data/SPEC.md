# Keytab Rotation Auditor — Output Contract

This file is part of the read-only input dataset under `/app/data/`. It defines exactly how the five output JSON files at `/app/audit/` must be derived from the inputs. Every requirement in this file is binding.

## Time model

A timestamp is the ordered pair `(day, hour)` with `0 <= hour < 24`. Comparison is lexicographic: `(d1, h1) < (d2, h2)` iff `d1 < d2`, or `d1 == d2` and `h1 < h2`. `pool_state.current_day` and `pool_state.current_hour` give the audit-window cutoff; any event whose `(day, hour)` is strictly greater than `(current_day, current_hour)` is silently dropped.

## Event validation

The keytab events come from `events/keytab_chunk_*.jsonl`; the union of those files (in any order) is the keytab-event stream. Likewise for TGS requests under `events/tgs_chunk_*.jsonl`. The relative order within the audit is determined by `(day, hour, event_id)` ascending — `event_id` is an ASCII string and ties on `(day, hour)` are broken by ASCII order of `event_id`.

A **keytab event** is **valid** iff **all** of the following hold:

- `event_id` is a non-empty string and is unique across the entire keytab-event stream.
- `kind` is one of `"add"`, `"revoke"`, `"retire"`.
- `principal` matches the `principal` field of some entry in `principals/` (read the per-principal files; their union, sorted alphabetically by `principal`, is the principal table).
- `kvno` is an integer with `1 <= kvno <= 99999`.
- `day` is a non-negative integer; `hour` is an integer with `0 <= hour < 24`.
- For `kind == "add"`: `enctype` is a non-empty string.
- For `kind == "revoke"`: `reason` is one of `"compromise"`, `"expired"`, `"policy_violation"`, `"administrative"`.
- `(day, hour) <= (pool_state.current_day, pool_state.current_hour)`.

A **TGS request** is **valid** iff **all** of the following hold:

- `request_id` is a non-empty string and is unique across the entire TGS-request stream.
- `principal` matches some `principal` in the principal table.
- `kvno` is an integer with `1 <= kvno <= 99999`.
- `day` is a non-negative integer; `hour` is an integer with `0 <= hour < 24`.
- `(day, hour) <= (pool_state.current_day, pool_state.current_hour)`.

Invalid keytab events and invalid TGS requests are silently dropped from every downstream computation but are counted as `summary.invalid_keytab_events` and `summary.invalid_tgs_requests` respectively.

## Per-principal kvno lifecycle

For each principal `P`, process the valid keytab events for `P` in `(day, hour, event_id)` ascending order, maintaining a per-principal map `state[K]` from kvno integer `K` to a record. Each record has the fields:

- `kvno` (int)
- `added_day`, `added_hour` (int)
- `enctype` (string)
- `revoked_day`, `revoked_hour`, `revoke_reason` (int|null, int|null, string|null)
- `retired_day`, `retired_hour` (int|null, int|null)
- `final_state` (one of `"active"`, `"revoked"`, `"retired"`)

Apply each event:

1. `"add"`: if `state[K]` already exists, the event is a **monotonicity violation** and is otherwise ignored (the record is NOT created or overwritten); record anomaly `kvno_non_monotonic` (HIGH). Otherwise, if `K` is not strictly greater than every existing key in `state`, the event is a monotonicity violation and is otherwise ignored; record anomaly `kvno_non_monotonic` (HIGH). Otherwise, create `state[K]` with the `added_day`, `added_hour`, and `enctype` from the event; `revoke_*` and `retire_*` are null; `final_state` starts as `"active"`.

2. `"revoke"`: if `state[K]` does not exist, the event is an **unknown-target violation** and is otherwise ignored; record anomaly `revoke_unknown_kvno` (MEDIUM). Otherwise, if `state[K].final_state != "active"`, the event is a **redundant-state violation** and is otherwise ignored; record anomaly `revoke_already_terminal` (LOW). Otherwise, set `state[K].revoked_day`, `state[K].revoked_hour`, `state[K].revoke_reason` from the event and set `state[K].final_state = "revoked"`.

3. `"retire"`: if `state[K]` does not exist, the event is an **unknown-target violation** and is otherwise ignored; record anomaly `retire_unknown_kvno` (MEDIUM). Otherwise, if `state[K].final_state != "active"`, the event is a **redundant-state violation** and is otherwise ignored; record anomaly `retire_already_terminal` (LOW). Otherwise, set `state[K].retired_day`, `state[K].retired_hour` from the event and set `state[K].final_state = "retired"`.

A monotonicity-violating add, an unknown-target revoke/retire, and a redundant-state revoke/retire all leave the prior `state[K]` (if any) entirely unchanged.

## Active and current sets

At any timestamp `t = (d, h)`, define the **active set** of principal `P` as every `K` for which:

- `(state[K].added_day, state[K].added_hour) <= t`, AND
- either `state[K].revoked_day == null` or `t < (state[K].revoked_day, state[K].revoked_hour)`, AND
- either `state[K].retired_day == null` or `t < (state[K].retired_day, state[K].retired_hour)`.

The **current** kvno at `t` is `max(active set)`. If the active set is empty, the current kvno is `null`. A kvno `K` in the active set with `K != current` is **non-current active**.

## Cross-fade window

Read `cross_fade_hours` from `rotation_policy.cross_fade_hours`. Define the **cross-fade deadline** for a non-current active kvno `K` at time `t` (where the current kvno is `C`) as: `add_ts(C) + cross_fade_hours`, where `add_ts(C) = state[C].added_day * 24 + state[C].added_hour`. Convert `t` similarly to absolute hours. `K` is **in cross-fade at `t`** iff `t < add_ts(C) + cross_fade_hours`. A non-current active kvno that is NOT in cross-fade at `t` is **past cross-fade at `t`**.

## Rotation compliance

The rotation window for principal `P` is:

- if `P.exempt == true`, the rotation window is `null` and `P`'s status is `"exempt"`.
- else if `P.override_rotation_days != null`, the rotation window is `P.override_rotation_days`.
- else, the rotation window is `rotation_policy.tier_windows[P.tier]` (the lookup must succeed; if `P.tier` is not a key, the principal is invalid and contributes 1 to `summary.invalid_principals`, and is omitted from every output).

Define `add_events(P)` as the sequence of valid `"add"` events for `P` in `(day, hour, event_id)` order. `last_rotation_day(P)` is the `day` of the LAST event in that sequence, or `null` if the sequence is empty.

For a non-exempt principal with rotation window `W`:

- `next_due_day = last_rotation_day(P) + W` (if `last_rotation_day(P)` is not null).
- `status = "never_rotated"` if `last_rotation_day(P) == null`.
- `status = "overdue"` if `next_due_day < pool_state.current_day`.
- `status = "compliant"` otherwise.

Additional rotation anomalies:

- `missed_rotation` (MEDIUM) is recorded for every non-exempt principal with `status == "overdue"`. The anomaly's `(day, hour)` is `(pool_state.current_day, 0)` and `kvno` is `null`.
- `never_rotated` (HIGH) is recorded for every non-exempt principal with `status == "never_rotated"`. The anomaly's `(day, hour)` is `(pool_state.current_day, 0)` and `kvno` is `null`.
- `excessive_rotation` (LOW) is recorded for principal `P` iff there exist two distinct valid `"add"` events `E1` and `E2` for `P` with `E2.day * 24 + E2.hour - E1.day * 24 - E1.hour < ceil(W * 24 / 2)` and `(E1.day, E1.hour) < (E2.day, E2.hour)`. At most one `excessive_rotation` per principal is recorded — use the EARLIEST such `E2` (in `(day, hour, event_id)` order) and set the anomaly's `(day, hour, kvno)` to `(E2.day, E2.hour, E2.kvno)`. Exempt principals never trigger this.

## Enctype policy

`enctype_policy.json` lists policy versions in any order. Each version has an integer `effective_day`, a list `allowed_enctypes`, and a list `forbidden_enctypes`. The policy versions sorted by `effective_day` ascending form the policy timeline. The policy version **effective at day `d`** is the version with the largest `effective_day <= d`; if no such version exists, the principal `forbidden_enctype_active` and `weak_enctype` checks both treat the enctype as ALLOWED (no policy applies).

An enctype `E` is **allowed under version `V`** iff `E in V.allowed_enctypes` AND `E not in V.forbidden_enctypes`. (If both lists contain the same enctype, forbidden wins.)

`forbidden_enctype_active` (MEDIUM) is recorded for every `(P, K)` where `state[K].final_state == "active"` (as of `pool_state.current_day`) AND `state[K].enctype` is NOT allowed under the policy version effective at `pool_state.current_day`. One anomaly per `(P, K)`; the anomaly's `(day, hour)` is `(pool_state.current_day, 0)`.

## Compromise propagation

A principal `P` is **compromised** iff at least one of `state[K]` for `P` has `final_state == "revoked"` and `revoke_reason == "compromise"`. The list `compromised_principals` in `summary.json` is the sorted-ascending list of compromised principal names.

For every valid TGS request whose `principal` is compromised, ALSO record `compromised_principal_referenced` (CRITICAL). This anomaly is recorded **in addition to** any verdict-derived anomaly and uses `(day, hour, kvno)` from the request itself.

## Ticket validity

For each valid TGS request with `principal = P`, `kvno = K`, `day = d`, `hour = h`, determine `t = (d, h)`. Compute the active set for `P` at `t` as defined above. Let `policy_version_id` be the `version` field of the enctype policy effective at `d` (or `"none"` if no policy applies). The verdict is determined by the FIRST matching rule below (rules evaluated top-down):

1. If `state[K]` does not exist for `P` at `t` (i.e., no `"add"` event for `K` has happened by `t`): verdict = `"invalid_kvno_unknown"`. Anomaly: `ticket_unknown_kvno` (HIGH).
2. If `state[K].revoked_day != null` and `(state[K].revoked_day, state[K].revoked_hour) <= t`: verdict = `"invalid_kvno_revoked"`. Anomaly: `ticket_against_revoked` (CRITICAL).
3. If `state[K].retired_day != null` and `(state[K].retired_day, state[K].retired_hour) <= t`: verdict = `"invalid_kvno_retired"`. Anomaly: `ticket_against_retired` (MEDIUM).
4. If `state[K].enctype` is NOT allowed under the policy version effective at `d`: verdict = `"weak_enctype"`. Anomaly: `weak_enctype_in_use` (HIGH).
5. If `K` is the current kvno at `t`: verdict = `"valid"`. No anomaly.
6. If `K` is in cross-fade at `t`: verdict = `"valid_cross_fade"`. No anomaly.
7. Otherwise (`K` is past cross-fade at `t`): verdict = `"downgrade_attempt"`. Anomaly: `downgrade_attempt` (HIGH).

The verdict-derived anomaly's `(day, hour, kvno)` is `(d, h, K)`.

`missed_retirement` (MEDIUM) is recorded for every `(P, K)` where `K` is non-current active at `t = (pool_state.current_day, pool_state.current_hour)` AND `K` is past cross-fade at `t`. The anomaly's `(day, hour, kvno)` is `(pool_state.current_day, pool_state.current_hour, K)`.

## Anomaly ordering

`anomalies.json` lists every anomaly recorded above, in this exact sort order: severity rank descending (`critical` > `high` > `medium` > `low`), then `day` ascending, then `hour` ascending, then `kind` ascending (ASCII), then `principal` ascending (ASCII), then `kvno` ascending with `null` last.

Each anomaly's `id` is the lowercase hexadecimal SHA-256 of the UTF-8 bytes of the canonical JSON `{"kind":<kind>,"principal":<principal>,"kvno":<kvno-or-null>,"day":<day>,"hour":<hour>}` (the canonicalisation is `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`).

## Output schemas

All five outputs are written under `/app/audit/`. List ordering is part of the contract.

### `/app/audit/kvno_lifecycle.json`

```
{"principals": [
  {"principal": "...",
   "tier": "...",
   "exempt": <bool>,
   "kvno_events": [
     {"kvno": <int>, "added_day": <int>, "added_hour": <int>, "enctype": "...",
      "revoked_day": <int>|null, "revoked_hour": <int>|null, "revoke_reason": "..."|null,
      "retired_day": <int>|null, "retired_hour": <int>|null,
      "final_state": "active"|"revoked"|"retired"}
   ]}
]}
```

`principals` is sorted by `principal` ascending. `kvno_events` is sorted by `kvno` ascending. Each kvno appearing in `state[*]` for the principal appears exactly once. Invalid principals (unknown `tier`) are omitted entirely.

### `/app/audit/rotation_compliance.json`

```
{"principals": [
  {"principal": "...",
   "tier": "...",
   "exempt": <bool>,
   "rotation_window_days": <int>|null,
   "last_rotation_day": <int>|null,
   "next_due_day": <int>|null,
   "status": "compliant"|"overdue"|"exempt"|"never_rotated"}
]}
```

`principals` is sorted by `principal` ascending. For exempt principals, `rotation_window_days`, `last_rotation_day`, and `next_due_day` are all null and `status` is `"exempt"`. For `never_rotated`, `last_rotation_day` and `next_due_day` are null. Invalid principals are omitted.

### `/app/audit/ticket_validity.json`

```
{"requests": [
  {"request_id": "...",
   "principal": "...",
   "kvno": <int>,
   "day": <int>,
   "hour": <int>,
   "verdict": "valid"|"valid_cross_fade"|"invalid_kvno_unknown"|"invalid_kvno_revoked"|"invalid_kvno_retired"|"downgrade_attempt"|"weak_enctype",
   "policy_version": "..."}
]}
```

`requests` is sorted by `(day, hour, request_id)` ascending — same ordering as the temporal evaluation order. Each valid TGS request appears exactly once. Invalid TGS requests are omitted. Requests for invalid principals are also omitted (they contribute to `summary.invalid_tgs_requests`).

### `/app/audit/anomalies.json`

```
{"anomalies": [
  {"id": "<sha256-hex>",
   "kind": "...",
   "severity": "critical"|"high"|"medium"|"low",
   "principal": "...",
   "kvno": <int>|null,
   "day": <int>,
   "hour": <int>,
   "details": "..."}
]}
```

`anomalies` is sorted as documented in "Anomaly ordering". The `details` string is a single-line human-readable summary; its exact text is canonicalised by this rule: it is exactly `"<kind> on <principal>"` when `kvno` is null, otherwise exactly `"<kind> on <principal> kvno=<kvno>"`.

### `/app/audit/summary.json`

```
{"current_day": <int>,
 "current_hour": <int>,
 "total_principals": <int>,
 "exempt_principals": <int>,
 "invalid_principals": <int>,
 "total_keytab_events": <int>,
 "invalid_keytab_events": <int>,
 "total_tgs_requests": <int>,
 "invalid_tgs_requests": <int>,
 "tickets_per_verdict": {"<verdict>": <int>},
 "anomalies_per_severity": {"critical": <int>, "high": <int>, "medium": <int>, "low": <int>},
 "compromised_principals": ["..."]}
```

`tickets_per_verdict` contains every one of the seven verdict strings as a key (zero if no requests had that verdict) with keys sorted ascending. `anomalies_per_severity` always contains the four severity keys with keys sorted ascending. `compromised_principals` is sorted ascending. `total_principals` counts every entry in the principal table (invalid included); `invalid_principals` counts those omitted from the outputs due to an unknown `tier`. `total_keytab_events` is the COUNT of records read across `events/keytab_chunk_*.jsonl` (before validation); `invalid_keytab_events` is the COUNT dropped during validation. Same for TGS.

All outputs are UTF-8, indented with two spaces, with object keys emitted in sorted order at every level, and end in a single trailing newline. Every list field follows the sort order specified above so that two correct implementations of the same contract produce byte-identical files for the same input.
