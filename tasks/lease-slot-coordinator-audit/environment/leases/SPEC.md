# Lease slot coordinator audit (normative)

All inputs are UTF-8 JSON. The audit day is `pool_state.current_day` (integer). Never mutate anything under `/app/leases/`.

## Host and slot inputs

Each file `hosts/<host_id>.json` defines `host_id` (string, equals filename stem), `tier` ∈ {`gold`,`silver`,`bronze`}, `renewals_by_day` (object mapping decimal day strings to non-negative integers), and `leases` (array). Each lease object has `slot_id`, `lease_until_day` (int), `renew_count` (int), `last_renew_day` (int).

Each file `slots/<slot_id>.json` defines `slot_id` (equals stem), `capacity` (int ≥ 1), and optional `witness_quorum_override` (int ≥ 0). If omitted, quorum comes from policy.

Each file `witnesses/<slot_id>.json` defines `slot_id` and `attestations` (array). Each attestation has `witness_host`, `subject_host`, `day` (int). Duplicate triples in one file are ignored (keep first in file order).

## Rolling renewal window

Let `W = policy.renewal_window_days` (≥ 1). The inclusive window is every integer `d` with `current_day - (W - 1) <= d <= current_day`. For a host, `window_renewals` is the sum of `renewals_by_day` values whose day key parses to an integer in the window; absent keys contribute 0.

Let `renewal_window_lo = current_day - (W - 1)`.

## Witness-only day floor

If `policy.witness_day_floor` is present and parses as an integer, let `F` be that value; if absent, `F` is 0. Witness attestation days use inclusive lower bound `witness_lo = max(renewal_window_lo, F)` and inclusive upper bound `current_day`. This bound applies only to witness day filtering; `window_renewals` still uses `renewal_window_lo` through `current_day` unchanged.

## Incidents

Read `incident_log.events`. Keep only events with `accepted == true` and `event.day <= current_day`. Sort kept events by ascending `(day, event_id)` and process in that order.

Supported `kind` values:

- `extend_grace`: fields `target_tier` ∈ {`gold`,`silver`,`bronze`} and integer `extra_days`. Add `extra_days` to the running grace allowance for that tier (additive across events).
- `renewal_cap_delta`: fields `target_tier` and integer `delta`. Add `delta` to the running max-renewal cap for that tier (additive).
- `freeze_renewals`: field `host_id`. While present among kept events, every lease whose `host_id` equals this value is forced to `computed_status` `frozen` unless a higher-precedence rule below applies. `renewal_blocked` must be true.
- `slot_compromise`: field `slot_id`. Every lease on this slot is forced to `quarantined` regardless of dates or witnesses.
- `host_compromise`: field `host_id`. Every lease for this host is forced to `quarantined`.
- `force_expire`: fields `host_id` and `slot_id`. After other numeric work, that lease must be `expired` with `reasons` containing `force_expire_incident` (even if other reasons also apply).

Unknown kinds or missing required fields: ignore the event.

## Policy knobs

`renewal_window_days` is required (≥ 1). Optional `witness_day_floor` (integer); when absent, treat as 0 for witness lower-bound math only.

## Tier baselines

`base_grace = policy.grace_days_by_tier[tier]` plus all applied `extend_grace.extra_days` for that tier.

`base_max_renewals = policy.max_renewals_by_tier[tier]` plus all applied `renewal_cap_delta.delta` for that tier. After sums, clamp to minimum 0.

`quorum = slot.witness_quorum_override` if present in the slot file, else `policy.witness_quorum_by_tier[tier]`.

## Slot contention

For each `slot_id`, count distinct `host_id` values among all leases referencing that slot (across all host files). `contested` is true when the count is ≥ 2.

## Witness sufficiency (contested slots only)

When `contested` is false, witness checks pass.

When contested, build the set `cohosts(S)` of every `host_id` that appears on any lease with `slot_id == S` across all host files.

For a lease on subject host `H` and slot `S`, consider attestations in `witnesses/S.json` where `subject_host == H`, `witness_host != H`, `witness_host` is an element of `cohosts(S)`, and `witness_lo <= day <= current_day`. Deduplicate by `(witness_host, day)` using the first attestation in file order for each pair. Let `witness_score` be the number of deduplicated pairs. Sufficiency holds when `witness_score >= quorum`. Otherwise the lease is `witness_pending` (unless quarantined, frozen, or forced expired first).

`witness_pairs_credited` on each lease row is 0 when witness sufficiency is not evaluated for that lease (rules 1–3 matched first, or the slot is uncontested). Otherwise it equals `witness_score` computed for that lease, including partial scores when insufficient.

## Status precedence (per lease)

Evaluate in order; first match wins:

1. `host_compromise` on this host, or `slot_compromise` on this slot → `quarantined`, `renewal_blocked` true.
2. Kept `force_expire` for this `(host_id, slot_id)` → `expired`, `renewal_blocked` true, reasons must include `force_expire_incident`.
3. Kept `freeze_renewals` for this host → `frozen`, `renewal_blocked` true.
4. If contested and witness insufficient → `witness_pending`, `renewal_blocked` true.
5. If `current_day > lease_until_day + base_grace` → `expired`, `renewal_blocked` true.
6. If `current_day > lease_until_day` → `grace`, `renewal_blocked` false.
7. If `renew_count >= base_max_renewals` → `renewal_capped`, `renewal_blocked` true.
8. Otherwise → `active`, `renewal_blocked` false.

## Reasons array

When status is `expired` and not solely from `force_expire_incident`, include `past_grace` if rule 5 would apply ignoring force. When status is `renewal_capped`, include `renewal_cap_reached`. When status is `witness_pending`, include `insufficient_witnesses`. When status is `grace`, emit empty reasons. For `quarantined`, `frozen`, and `active`, emit empty reasons unless `force_expire_incident` applies (only on forced expire).

`reasons` are strictly increasing ASCII, unique.

## Outputs (five files under `/app/audit/`)

Canonical JSON: UTF-8, two-space indent, ASCII only, keys sorted lexicographically at every object depth, colon plus single space, no trailing spaces on lines, exactly one trailing newline at EOF.

### lease_verdicts.json

- `leases`: array sorted by `(host_id asc, slot_id asc)`. Each object: `computed_status`, `effective_grace` (int), `host_id`, `lease_until_day`, `last_renew_day`, `max_renewals` (int), `renew_count`, `renewal_blocked` (bool), `reasons` (string array), `slot_id`, `tier`, `window_renewals` (int), `witness_pairs_credited` (int).

### tier_policy.json

- `tiers`: object with exactly keys `bronze`, `gold`, `silver`. Each value: `base_grace`, `grace_delta_sum`, `effective_grace`, `base_max_renewals`, `renewal_cap_delta_sum`, `effective_max_renewals`, `witness_quorum_default`.

### incident_journal.json

- `applied_events`: array in process order; each element includes `day`, `event_id`, `kind`, plus kind-specific optional fields (`target_tier`, `extra_days`, `delta`, `host_id`, `slot_id`). Omit unused keys. Keys sorted inside each object.

### slot_contention.json

- `slots`: map keyed by `slot_id` ascending. Each value: `capacity`, `contested` (bool), `active_hosts` (sorted host_id strings), `quorum_required` (int). `quorum_required` is the slot file's `witness_quorum_override` when present; otherwise `policy.witness_quorum_by_tier["bronze"]`.

### summary.json

- `leases_total`, `quarantined_leases`, `frozen_leases`, `witness_pending_leases`, `expired_leases`, `grace_leases`, `renewal_capped_leases`, `active_leases` (counts by final status), `contested_slots`, `applied_incident_events`, `ignored_incident_events`.

Count `ignored_incident_events` as events in the log that are not kept (rejected, future day, unknown kind, or missing fields).
