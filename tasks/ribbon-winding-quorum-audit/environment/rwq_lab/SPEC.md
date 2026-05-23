# Ribbon winding quorum audit

Normative rules for `/app/rwq_lab/` inputs and `/app/rwq_audit/` outputs. All JSON is UTF-8, ASCII-only strings, two-space indent, recursively sorted object keys, no trailing spaces on lines, exactly one trailing newline at EOF.

## Inputs

Read `policy.json`, `domain_layout.json`, `pool_state.json`, `index.json`, `incident_log.json`, `anchors/hi.json`, `anchors/lo.json`, and every relative path listed in `index.json.segments` under the data root.

- `policy.quorum_base` and `policy.crisis_quorum` are positive integers. `policy.winding_modulus` is an integer greater than or equal to 2. `policy.anchor_blend` is either `xor` or `or`. `policy.crisis_mode` is boolean. `policy.crisis_severity_floor` is a non-negative integer.
- `domain_layout.ribbon_bias` is an object mapping lane names to integers (missing lane implies 0).
- `pool_state.votes` maps slot names to non-negative integers. `pool_state.current_day` is a positive integer. Incidents with `day` strictly greater than `current_day` are ignored; all others are eligible.
- `anchors/*.mask_hex` is a hex string (optional `0x` prefix) denoting a 64-bit mask; pad to an even nybble count by prepending `0` when needed, then parse as big-endian hex.
- Each segment file contains `id`, `lane`, `winding` (non-negative integer), `weight` (ignored by the audit math but preserved in inputs), and `slot` (string).

## Incident replay

Sort eligible incidents by ascending `day`, then ascending `event_id`. Maintain `frozen_lanes` as a set of lane names, initially empty. Maintain `lane_carry` as lane-to-integer map, defaulting to 0. Maintain `crisis_triggered` boolean, initially false, and `crisis_trigger_day` as null until set.

Process incidents in sorted order. For each incident:

- `freeze_lane`: add every listed lane to `frozen_lanes`.
- `thaw_lane`: remove every listed lane from `frozen_lanes` if present.
- `pulse_carry`: add `bias` (integer, default 0 if absent) to `lane_carry[lane]` for every lane listed.

After applying the incident action, if `policy.crisis_mode` is true and `severity` is greater than or equal to `policy.crisis_severity_floor`, set `crisis_triggered` to true; on the first transition to true, set `crisis_trigger_day` to that incident day.

Emit `incident_effects.json` with key `applied`, an array of objects in application order, each with keys `action`, `day`, `event_id`, `lanes` (array of strings, may be empty), and `note` (`lanes marked frozen`, `lanes removed from frozen set`, or `lane carry updated`).

## Effective winding

Let `hi` and `lo` be the parsed anchor masks, `w` the segment winding as uint64.

- If `anchor_blend` is `xor`, `fused = hi ^ lo ^ w`.
- If `anchor_blend` is `or`, `fused = hi | lo | w`.

`effective_winding` is `int(fused % uint64(winding_modulus))`.

## Quorum need

Let `active_floor` be `policy.crisis_quorum` when `crisis_triggered` is true, otherwise `policy.quorum_base`. `quorum_need` equals `active_floor + effective_winding`.

## Per-segment evaluation

Let `bias` be `ribbon_bias[lane]` (0 if missing). Let `carry` be `lane_carry[lane]` (0 if missing). Let `votes_raw` be `votes[slot]` when the slot exists in `votes`, otherwise 0. `lane_bonus` is `bias + carry`. `effective_votes` is `votes_raw + lane_bonus`.

Determine `status` in this order:

1. If `lane` is in `frozen_lanes`, `status` is `lane_frozen` and `satisfied` is false.
2. Else if `slot` is absent from `votes`, `status` is `slot_missing` and `satisfied` is false.
3. Else if `effective_votes` is greater than or equal to `quorum_need`, `status` is `ok` and `satisfied` is true.
4. Else `status` is `short` and `satisfied` is false.

Emit `segment_quorum.json` with key `segments`, sorted by ascending `id`. Each segment object carries keys in ASCII order: `effective_votes`, `effective_winding`, `id`, `lane`, `lane_bonus`, `quorum_need`, `satisfied`, `status`, `votes_raw`, `winding`.

Emit `lane_summary.json` with key `lanes`, sorted by ascending `lane`. Each lane object has keys `frozen`, `lane`, `missing_slot`, `ok`, `segment_count`, `short`, counting segments by final `status` (`lane_frozen` increments `frozen`, `slot_missing` increments `missing_slot`, `ok` increments `ok`, `short` increments `short`).

Emit `summary.json` with `segments_total`, `satisfied_count`, `short_count`, `lane_frozen_count`, `missing_slot_count`, `crisis_triggered`, nullable `crisis_trigger_day`, `eligible_incidents`, `applied_incidents`, `anchor_blend`, `winding_modulus`, `quorum_base`, and `active_quorum_floor` (equals `active_floor` after replay). Lexicographic key order in the file must match: `active_quorum_floor`, `anchor_blend`, `applied_incidents`, `crisis_trigger_day`, `crisis_triggered`, `eligible_incidents`, `lane_frozen_count`, `missing_slot_count`, `quorum_base`, `satisfied_count`, `segments_total`, `short_count`, `winding_modulus`.
