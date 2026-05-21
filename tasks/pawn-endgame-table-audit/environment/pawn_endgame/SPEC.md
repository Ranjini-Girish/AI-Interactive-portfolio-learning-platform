# Pawn endgame tablebase slice audit (normative)

All JSON emitted to the audit directory must be UTF-8, pretty-printed with two-space indentation, sorted object keys at every object depth, comma separators without extra spaces beyond the two-space indent convention, and exactly one trailing newline after the closing brace. Use the equivalent of `json.MarshalIndent` with prefix `""` and indent `"  "` followed by a single newline, or match byte-for-byte the canonicalization tests.

## Paths and environment

Read-only inputs live under the directory named by `PET_DATA_DIR`, default `/app/pawn_endgame`. Write outputs only under `PET_AUDIT_DIR`, default `/app/audit`. Required input files are `SPEC.md`, `pool_state.json`, `manifest.json`, `policy/caps.json`, `policy/opposition_tiebreak.json`, `policy/tempo_policy.json`, `incidents/incident_log.json`, plus every relative path listed in `manifest.json` for `race_files`, `tempo_files`, and `grid_files`.

Emit exactly five files in the audit directory and no others: `passed_pawn_races.json`, `opposition_grid.json`, `tempo_loss_windows.json`, `underpromotion_caps.json`, `summary.json`.

## Frozen positions

Parse `incidents/incident_log.json`. Let `floor` be the integer `freeze_severity_floor`. A position id is **frozen** when it appears in `position_ids` of any incident where `severity` is greater than or equal to `floor` and `action` is exactly `freeze_illegal`. Frozen ids suppress distance and tie-break evaluation; they still appear in summary lists with deterministic sorting.

## Shared slice row

Each race, tempo, and grid fixture is a JSON object. Required integer fields are `white_rank` (1-8), `black_rank` (1-8), `white_file` (0-7), `black_file` (0-7), `tempo_moves` (non-negative integer), and `underpromotion_risk` (non-negative integer). Required string field `side_to_move` is either `w` or `b`. Required string field `position_id` is unique across all fixtures. Grid-only fixtures omit ranks only if absent; when ranks are absent, treat `white_rank` and `black_rank` as 4 and 4 for any formula that needs them.

## Passed pawn races (`passed_pawn_races.json`)

For each race file entry in manifest order, compute:

- `W = 8 - white_rank`
- `B = black_rank - 1`
- `adjW = W` minus 1 if `side_to_move` is `w`, else `adjW = W`
- `adjB = B` minus 1 if `side_to_move` is `b`, else `adjB = B`

If the `position_id` is frozen, output `outcome` of `frozen`, `plies_to_decisive` 0, `reason_codes` as the single-element array `["incident_freeze"]`.

Otherwise, if `adjW < adjB`, outcome `white_wins` with `reason_codes` `["distance_decisive"]`. If `adjB < adjW`, outcome `black_wins` with the same reason list.

If `adjW == adjB`, form `cell_key` as the string `f` concatenated with decimal `abs(white_file - black_file) % 5`, then `_m`, then decimal `tempo_moves % 2`. Load `policy/opposition_tiebreak.json` object `tiebreak_table` map from `cell_key`. The map value is an object with keys `w` and `b` whose values are each one of `white_wins`, `black_wins`, or `draw`. Let `mover` be `w` or `b` matching `side_to_move`. The race `outcome` is the string stored at that key. `reason_codes` is `["opposition_tiebreak"]`.

`plies_to_decisive` is `adjW + adjB + tempo_moves` when the branch was distance decisive; when the branch was opposition tie-break, `plies_to_decisive` is `2*adjW + abs(white_file - black_file) + tempo_moves`.

The top-level object has key `races` whose value is an array of objects with keys `plies_to_decisive`, `position_id`, `outcome`, `reason_codes` (array of strings sorted lexicographically). Sort the `races` array by `position_id` ascending.

## Tempo loss windows (`tempo_loss_windows.json`)

Read `window_size` as positive integer `W`, array `exposed_remainders` of integers each in `[0, W-1]`, and integer `carry_threshold`. For each tempo file entry:

If frozen: `class` is `frozen`, `window_index` is -1, `carry_pressure` false, `remainder` 0.

Else: `remainder = tempo_moves % W`, `window_index = floor(tempo_moves / W)` using integer division toward zero for non-negative inputs. `class` is `exposed` if `remainder` is an element of `exposed_remainders` (test membership against the JSON array values exactly), otherwise `safe`. `carry_pressure` is true if and only if `tempo_moves` is greater than or equal to `carry_threshold`.

Each record includes `position_id`, `class`, `window_index`, `remainder`, `carry_pressure`. Sort the output array `windows` by `position_id`.

## Underpromotion caps (`underpromotion_caps.json`)

From `policy/caps.json`, read `default_underpromotion_cap`, object `rank_overrides` whose keys are decimal rank strings, and integer `illegal_combo_multiplier` at least 1.

For each race and tempo fixture (grid-only fixtures are skipped here), compute `cap` as `rank_overrides` value for the decimal string of `white_rank` if present, otherwise `default_underpromotion_cap`. Compute `demand = underpromotion_risk + ((white_rank + black_rank) % 5)`.

If frozen: `cap_band` is `frozen`, `effective_cap` is -1.

Else if `demand <= cap`: `cap_band` is `within_cap` and `effective_cap` is `cap`.

Else if `demand <= cap * illegal_combo_multiplier`: `cap_band` is `exceeds_cap` and `effective_cap` is `cap`.

Else: `cap_band` is `beyond_policy` and `effective_cap` is `cap`.

Sort the output array `evaluations` by `position_id`.

## Opposition grid (`opposition_grid.json`)

Consider every race, tempo, and grid fixture. Drop any whose `position_id` is frozen. For each remaining row compute the same `cell_key` as in races. Build a map from `cell_key` to the sorted unique list of `position_id` values seen. Emit array `cells` of objects with keys `cell_key`, `member_positions` (sorted array of strings), `verdict_if_white_moves`, `verdict_if_black_moves` copied from `tiebreak_table[cell_key]` keys `w` and `b`. If a `cell_key` is missing from the table, both verdicts are `draw`. Sort `cells` by `cell_key` ascending.

## Summary (`summary.json`)

Include string `audit_epoch` copied from `pool_state.json` field `audit_epoch`. Include object `counts` with non-negative integers: `races_total`, `races_frozen`, `races_white_wins`, `races_black_wins`, `races_draw`, `tempo_exposed`, `tempo_safe`, `tempo_frozen`, `grid_cells`, `caps_within`, `caps_exceeds`, `caps_beyond`, `caps_frozen`. Counts derive from the emitted race, tempo, cap, and opposition outputs. Include sorted array `frozen_position_ids` listing every frozen id. Include object `incident_actions` mapping each distinct `action` string from the incident list to its occurrence count. Numeric fields in `counts` must match the tallies implied by the other four audit files.
