# Normative specification — `tbr_lat` bundle

All paths below are relative to `/app/tbr_lat/` unless noted. Read JSON in UTF-8. Lists that represent deterministic bundles must be sorted as stated before serialization.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `incident_log.json`, every `items/*.json` file in ascending ASCII filename order, `anchors/a.json`, `anchors/b.json`, and `ancillary/x.json`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing mirrors the harness: when `PREFIX_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/tbr_lat/`; when `PREFIX_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. Replace `PREFIX` with the three-letter code from the task instruction.

## Incident common shape

`incident_log.json` contains an `events` array. Only events with `"accepted": true` apply. Unless a task section says otherwise, ignore unknown fields without error.


## Thompson-style rank audit

Items have string `arm_id`, integer `successes`, integer `failures`. Each accepted `observe_win` incident increments successes for the matching `arm_id` before scoring.

Integer score is `((successes_effective + 1) * 1_000_000) // (successes_effective + failures + 2)` using the effective success counts.

Emit `arm_rank.json` with `ranked` array sorted by descending `score` then ascending `arm_id`, each row listing `arm_id`, `successes_effective`, `failures`, `score`, plus `order` array of arm ids in that rank order. Emit `summary.json` with integer `arms` and `current_day`.
