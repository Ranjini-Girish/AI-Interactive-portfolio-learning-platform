# Normative specification — `clf_lat` bundle

All paths below are relative to `/app/clf_lat/` unless noted. Read JSON in UTF-8. Lists that represent deterministic bundles must be sorted as stated before serialization.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `incident_log.json`, every `items/*.json` file in ascending ASCII filename order, `anchors/a.json`, `anchors/b.json`, and `ancillary/x.json`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing mirrors the harness: when `PREFIX_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/clf_lat/`; when `PREFIX_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. Replace `PREFIX` with the three-letter code from the task instruction.

## Incident common shape

`incident_log.json` contains an `events` array. Only events with `"accepted": true` apply. Unless a task section says otherwise, ignore unknown fields without error.


## Credit leak floor audit

`policy.floors` maps `user_class` strings to minimum float balances. Each item has `user_id`, `user_class`, float `daily_cred`, float `spent`.

Integer `current_day` comes from `pool_state.json`. For each user sum float `amount` from accepted `credit_grant` incidents sharing the `user_id`.

Raw balance is `daily_cred * current_day - spent + grants`. Final `balance` is the greater of raw balance and the class floor. `floor_hit` is true when raw balance is less than or equal to the floor.

Round `balance` to four decimal places using ties-to-even rounding identical to the reference harness.

Emit `cred_ledger.json` with `users` sorted by `user_id` containing `user_id`, `user_class`, `balance`, `floor_hit`. Emit `summary.json` with integer `users` and `current_day`.
