# Normative specification — `cfc_lat` bundle

All paths below are relative to `/app/cfc_lat/` unless noted. Read JSON in UTF-8. Lists that represent deterministic bundles must be sorted as stated before serialization.

## Global I/O contract

The audit reads `policy.json`, `pool_state.json`, `incident_log.json`, every `items/*.json` file in ascending ASCII filename order, `anchors/a.json`, `anchors/b.json`, and `ancillary/x.json`. Emit UTF-8 JSON under `/app/audit/` using `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))` followed by a single trailing newline for every file.

Environment routing mirrors the harness: when `PREFIX_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/cfc_lat/`; when `PREFIX_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. Replace `PREFIX` with the three-letter code from the task instruction.

## Incident common shape

`incident_log.json` contains an `events` array. Only events with `"accepted": true` apply. Unless a task section says otherwise, ignore unknown fields without error.


## CPM float chain audit

Items are tasks with string `task_id`, integer `duration_days`, and nullable string `predecessor` referencing another item `task_id`. The graph is acyclic; treat a null predecessor as no inbound edge.

Sum integer `add_days` from every accepted `stretch_task` incident per `task_id` and add that sum to the item duration before any scheduling math.

Compute forward early times: topological order breaking ties by ascending `task_id`. `early_start` is the maximum early finish of predecessors or zero. `early_finish` is `early_start + duration_days`. `project_end` is the maximum early finish.

Backward pass in reverse topological order: for tasks without successors set latest finish to `project_end`. Otherwise latest finish is the minimum of successor latest finishes minus that successor duration. `float_days` is latest finish minus `early_finish`.

Emit `cpm_schedule.json` with `tasks` sorted by `task_id` and fields `task_id`, `predecessor`, `duration_days`, `early_start`, `early_finish`, `float_days`, plus top-level `project_end`. Emit `summary.json` with integer `tasks` and `current_day`.
