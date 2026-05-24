# Normative specification — `bsp_lat` bundle

All paths below are relative to `/app/bsp_lat/` unless noted. Read JSON in UTF-8. Lists that represent deterministic bundles must be sorted as stated before serialization.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `incident_log.json`, every `items/*.json` file in ascending ASCII filename order, `anchors/a.json`, `anchors/b.json`, and `ancillary/x.json`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing mirrors the harness: when `PREFIX_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/bsp_lat/`; when `PREFIX_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. Replace `PREFIX` with the three-letter code from the task instruction.

## Incident common shape

`incident_log.json` contains an `events` array. Only events with `"accepted": true` apply. Unless a task section says otherwise, ignore unknown fields without error.


## Beam split phaser audit

Each item has string `beam_id`, integer `phase_deg` in `[0, 359]`, and positive integer `weight`. Sum accepted `nudge_beam` incident `delta_deg` values per `beam_id` and reduce modulo 360 before applying.

`phase_effective` is `(phase_deg + nudge) % 360`. Let `num = sum(phase_effective * weight)` and `den = sum(weight)` across items. `combined_phase` is `(num // den) % 360` when `den` is positive, otherwise zero.

Emit `beam_combine.json` with `beams` sorted by `beam_id` containing `beam_id`, `phase_effective`, `weight`, plus `combined_phase`. Emit `summary.json` with integer `beams` and `current_day`.
