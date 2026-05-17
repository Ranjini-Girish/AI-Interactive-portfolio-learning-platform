Normative contract for the dungeon trap-grid reconciliation audit. Inputs are UTF-8 JSON with ASCII-only strings. Outputs are UTF-8 JSON, ASCII-only, two-space indentation, recursively sorted object keys at every depth, no trailing spaces at line ends, and exactly one trailing newline after each root closing brace.

Read `policy.json` for integer `current_day`, integer `chain_max_hops`, integer `rearm_cooldown_days`, integer `hot_cooloff_days`, string `party_tier` (`gold`, `silver`, or `bronze`), and object `tier_disarm_cap` mapping each tier name to an integer disarm ceiling. Read `links.json` for array `edges` of objects `{a, b}` naming trap ids; treat every edge as undirected. Read `rooms.json` for array `rooms` of objects `{room_id, trap_ids}` listing traps in that room. Read `incidents.json` for array `events` with integer `day`, string `kind`, and optional `room_id` or `trap_id`. Enumerate every `*.json` file directly under `traps/`; each object provides string `trap_id`, string `room_id`, integer `difficulty`, boolean `armed`, boolean `initial_pulse`, and integer or null `last_trigger_day`. Files under `anchors/` and `manifest/` are packaging stubs only.

Process incidents after sorting by ascending `day`, then ascending `room_id` when present, otherwise ascending `trap_id`. Only events with `day` less than or equal to `current_day` apply. Supported kinds are `room_seal` (requires `room_id`), `force_pulse` (requires `trap_id`), and `disarm_boost` (no target fields). All other kinds are ignored.

A trap is sealed when any accepted `room_seal` names its `room_id`. Sealed traps never enter the trigger waves and always use final state `sealed` and disarm status `blocked_sealed`.

Let `boost` be one when any accepted `disarm_boost` has `day` equal to `current_day`, otherwise zero. Define `effective_disarm_cap` as `tier_disarm_cap[party_tier]` plus `boost` (missing tier keys are invalid input).

Initial pulse set: every trap that is not sealed, is `armed`, and either has `initial_pulse` true or has an accepted `force_pulse` naming its `trap_id`. Remove a trap from this set when `last_trigger_day` is not null, `current_day - last_trigger_day` is strictly less than `rearm_cooldown_days`, and no accepted `force_pulse` names that trap. Sort the surviving ids ascending; this is wave zero.

Chain propagation: maintain `triggered` as a set starting with wave zero. For `hop` from one through `chain_max_hops`, form the next wave from every undirected neighbor of any trap in the previous wave that is not sealed, not already in `triggered`, and `armed`. Append neighbors to `triggered` and record their hop index. Stop early when a wave would be empty. Each wave list is sorted ascending by `trap_id`.

For every trap, set integer `chain_hops` to its hop index when triggered, otherwise `-1`. Final state precedence (first match): `sealed` when sealed; else `triggered` when in `triggered`; else `cooldown_suppressed` when `armed`, `initial_pulse` true, not sealed, not in `triggered`, and rearm cooldown blocks it; else `disarmed_idle` when not `armed`; else `armed_idle`.

Disarm evaluation runs in trap id order. Status precedence: `blocked_sealed` when sealed; `not_applicable` when not `armed`; `blocked_hot` when final state is `triggered` and `current_day - last_trigger_day` is strictly less than `hot_cooloff_days` (when `last_trigger_day` is null use `current_day` as the trigger day for this comparison); `blocked_difficulty` when `difficulty` is greater than `effective_disarm_cap`; else `disarmed`.

Room status precedence per `room_id`: `sealed` when the room has any accepted `room_seal`; else `hazardous` when any trap in the room has final state `triggered`; else `cleared` when every trap in the room has final state `armed_idle` or `disarmed_idle`; else `partial`.

Emit `trap_states.json` with `current_day` copied from policy and `traps` sorted by `trap_id` ascending. Each row includes `chain_hops`, `difficulty`, `final_state`, `room_id`, and `trap_id`.

Emit `trigger_plan.json` with `waves`, an array of trap id arrays in hop order (wave zero first).

Emit `disarm_plan.json` with integer `effective_disarm_cap` and `entries` sorted by `trap_id` ascending; each entry has `difficulty`, `disarm_status`, and `trap_id`.

Emit `room_status.json` with `rooms` sorted by `room_id` ascending; each row has `room_id` and `status`.

Emit `summary.json` with integers `cooldown_suppressed_total`, `current_day`, `disarmed_total`, `hazardous_rooms`, `sealed_total`, `trap_total`, and `triggered_total` derived from the computed rows.

Read `TGC_DATA_DIR` defaulting to `/app/trapgrid` and `TGC_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
