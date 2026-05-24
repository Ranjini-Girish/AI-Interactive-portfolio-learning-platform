# FSM and workflow inputs

FSM definition files describe `initial_state`, `terminal_states`, and `allowed_edges` as pairs of state names. Workflow files list `transitions` with `transition_id`, `sequence`, `logged_at`, `from_state`, `to_state`, and optional `duration_ms`.

These inputs are read-only under `/app/data/`.
