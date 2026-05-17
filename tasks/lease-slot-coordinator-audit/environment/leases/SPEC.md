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

If `policy.witness_day_floor` is present and parses as an integer, let `F` be that value; if absent, `F` is 0. Let `witness_lo = max(renewal_window_lo, F)`. This bound applies only to witness day filtering; `window_renewals` still uses `renewal_window_lo` through `current_day` unchanged.

## Witness staleness

Let `S = policy.witness_staleness_days` (required integer ≥ 1). The effective witness inclusive lower day is `witness_eff_lo = max(witness_lo, current_day - S + 1)`. Attestations must satisfy `witness_eff_lo <= day <= current_day` to be day-eligible.

## Renewal burst limits

`policy.renewal_burst_limit_by_tier` is required with keys `bronze`, `gold`, and `silver` (each a non-negative integer). Compare `window_renewals` to the subject lease's tier limit only when evaluating burst throttling below.

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

`renewal_window_days` is required (≥ 1). `witness_staleness_days` is required (≥ 1). `renewal_burst_limit_by_tier` is required as above. Optional `witness_day_floor` (integer); when absent, treat as 0 for witness lower-bound math only.

## Tier baselines

`base_grace = policy.grace_days_by_tier[tier]` plus all applied `extend_grace.extra_days` for that tier.

`base_max_renewals = policy.max_renewals_by_tier[tier]` plus all applied `renewal_cap_delta.delta` for that tier. After sums, clamp to minimum 0.

## Witness quorum (two distinct values)

Do not mix these definitions; they answer different questions.

### Per-lease witness sufficiency (`sufficiency_quorum`)

For each lease on slot `S` whose subject host `H` has tier `T`:

- If `slots/S.json` includes `witness_quorum_override`, `sufficiency_quorum` equals that override.
- Otherwise `sufficiency_quorum = policy.witness_quorum_by_tier[T]` using the **subject host's** tier.

Use `sufficiency_quorum` only for status precedence step 4 (`witness_pending`), for `witness_pairs_credited` on leases that reach step 4, and for provisional cohost witness scoring. It is **per lease** and may differ across cohosts on the same contested slot.

### Reporting quorum (`quorum_required` in `slot_contention.json`)

`quorum_required` is **reporting metadata only**. It never drives lease status, provisional cohost passes, or witness sufficiency.

For each slot `S`:

- If `witness_quorum_override` is present in `slots/S.json`, `quorum_required` equals that override.
- Otherwise `quorum_required = policy.witness_quorum_by_tier["bronze"]` (the policy bronze-tier default, not any cohost's tier).

## Slot contention

For each `slot_id`, count distinct `host_id` values among all leases referencing that slot (across all host files). `contested` is true when the count is ≥ 2.

## Provisional cohost status (witness eligibility)

Before final witness scoring on a contested slot `S`, compute **provisional status** for every `(host_id, slot_id)` lease on `S` using the status precedence below but **skipping step 4** (treat witness sufficiency as passed for that provisional pass only). Do not apply witness eligibility filtering inside this provisional pass.

An attestation is **witness-eligible** when its `witness_host` is in `cohosts(S)` and the provisional status of that witness on `S` is not one of `witness_pending`, `frozen`, or `burst_throttled`. Quarantined provisional cohosts remain eligible witnesses.

## Witness sufficiency (contested slots only)

When `contested` is false, witness checks pass.

When contested, build `cohosts(S)` as every `host_id` on any lease with `slot_id == S`.

For subject host `H` on slot `S`, consider witness-eligible attestations in `witnesses/S.json` where `subject_host == H`, `witness_host != H`, `witness_host ∈ cohosts(S)`, and `witness_eff_lo <= day <= current_day`. Deduplicate by `(witness_host, day)` (first in file order). Let `witness_score` be the deduplicated pair count. Compute `sufficiency_quorum` for this lease as defined above. Sufficiency holds when `witness_score >= sufficiency_quorum`. Otherwise the lease is `witness_pending` unless a higher-precedence final rule applies first.

`witness_pairs_credited` is 0 when final evaluation never reaches step 4 (rules 1–3 matched, or the slot is uncontested). Otherwise it equals `witness_score`, including partial scores when insufficient.

## Status precedence (per lease)

Evaluate in order; first match wins:

1. `host_compromise` on this host, or `slot_compromise` on this slot → `quarantined`, `renewal_blocked` true.
2. Kept `force_expire` for this `(host_id, slot_id)` → `expired`, `renewal_blocked` true, reasons must include `force_expire_incident`.
3. Kept `freeze_renewals` for this host → `frozen`, `renewal_blocked` true.
4. If contested and witness insufficient (eligible attestations only) → `witness_pending`, `renewal_blocked` true.
5. If `current_day > lease_until_day + base_grace` → `expired`, `renewal_blocked` true.
6. If `current_day > lease_until_day` → `grace`, `renewal_blocked` false.
7. If `window_renewals > renewal_burst_limit_by_tier[tier]` → `burst_throttled`, `renewal_blocked` true.
8. If `renew_count >= base_max_renewals` → `renewal_capped`, `renewal_blocked` true.
9. Otherwise → `active`, `renewal_blocked` false.

## Reasons array

When status is `expired` and not solely from `force_expire_incident`, include `past_grace` if rule 5 would apply ignoring force. When status is `renewal_capped`, include `renewal_cap_reached`. When status is `burst_throttled`, include `renewal_burst_exceeded`. When status is `witness_pending`, include `insufficient_witnesses`. When status is `grace`, emit empty reasons. For `quarantined`, `frozen`, and `active`, emit empty reasons unless `force_expire_incident` applies (only on forced expire).

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

- `slots`: map keyed by `slot_id` ascending. Each value: `capacity`, `contested` (bool), `active_hosts` (sorted host_id strings), `quorum_required` (int). Populate `quorum_required` using the reporting-quorum rules above; do not substitute a cohost tier or a per-lease `sufficiency_quorum`.

### summary.json

- `leases_total`, `quarantined_leases`, `frozen_leases`, `witness_pending_leases`, `expired_leases`, `grace_leases`, `burst_throttled_leases`, `renewal_capped_leases`, `active_leases` (counts by final status), `contested_slots`, `applied_incident_events`, `ignored_incident_events`.

Count `ignored_incident_events` as events in the log that are not kept (rejected, future day, unknown kind, or missing fields).
