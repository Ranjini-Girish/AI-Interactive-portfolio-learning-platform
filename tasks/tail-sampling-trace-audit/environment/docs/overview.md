# Tail-Sampling Decision Engine — Overview

The simulator models the back-end of a distributed-tracing tail-sampler.
The agent ingests a flat list of spans (each carrying its `trace_id`,
`span_id`, `parent_span_id`, `service`, `operation`, integer
`start_unix_ms`, non-negative integer `duration_ms`, `status` from
`{"ok","error","timeout"}`, and a string-keyed string-valued
`attributes` map), groups them by `trace_id`, validates each trace,
evaluates a configured policy chain against it, and emits a single
`decision` of `"keep"` or `"drop"` per trace plus per-policy and
per-service rollups.

Span ids are 8-hex-char strings, trace ids are 16-hex-char strings, and
every span's `parent_span_id` either is `null` (root) or names a span
that is also present in the same trace. Spans inside the input file
arrive in no particular order; the simulator first groups them by
`trace_id` and then sorts each trace's span list by `(start_unix_ms,
span_id)` for any per-span iteration the spec needs.

The processing pipeline is:

1. Group input spans by `trace_id`.
2. For each trace, run the trace-level validation chain documented in
   `validation.md` (cycle / multi_root / incomplete / orphan), in that
   exact precedence order. The first failing check drives the decision
   via its `*_action` from `config.json` and emits the corresponding
   diagnostic. The remaining checks still emit their diagnostics but do
   NOT override the decision.
3. If no validation check failed, evaluate the policy chain in
   `policies.json` order. The first matching policy wins; its `action`
   (or, for probabilistic, its per-trace bucket result) becomes the
   decision and its `name` is recorded as `matched_policy`. When no
   policy matches the decision is `"drop"` and `reason` is
   `"no_policy_matched"`.
4. Compute the per-span `D_FUTURE_TIMESTAMP` diagnostic independently
   of the decision: every span whose `start_unix_ms - now_unix_ms`
   strictly exceeds `future_timestamp_threshold_ms` gets one entry. The
   diagnostic never overrides a decision.
5. Roll up per-policy and per-service stats and the global summary.

All five output files are byte-exact canonical JSON; see
`output_format.md` and `diagnostics.md` for the closed code set and the
sort orders.
