# Trace-Level Validation

For every distinct `trace_id` the simulator runs four checks in this
strict precedence order. The FIRST check that fails owns the decision
(its `*_action` from `config.json` is used and the `reason` field
records the failing check). The remaining checks still emit their own
diagnostics so the diagnostic stream is complete, but they do NOT
override the decision.

## 1. cycle_detected — `reason = "cycle_detected"`

Build the span DAG using each span's `parent_span_id` as the edge to its
parent. A trace fails this check if the graph induced over its spans
has any cycle — that is, following parent pointers from some span lands
back on itself without first hitting a span whose `parent_span_id` is
`null`.

When this fires, the decision is `config.cycle_action`; the diagnostic
is `D_CYCLE_DETECTED` (span_id null, evidence.`cycle_span_ids` is the
sorted-ASCII span_id list of the cycle's vertices).

## 2. multi_root — `reason = "multi_root"`

A well-formed trace has exactly one span with `parent_span_id == null`.
If the trace has two or more such spans the check fails. When this
fires, the decision is `config.multi_root_action`; the diagnostic is
`D_MULTI_ROOT` (span_id null, evidence.`root_span_ids` is the
sorted-ASCII list of every root span_id).

## 3. incomplete_trace — `reason = "incomplete_trace"`

If the trace's span count is strictly less than
`config.min_spans_per_trace` the check fails. When this fires, the
decision is `config.incomplete_action`; the diagnostic is
`D_INCOMPLETE_TRACE` (span_id null,
evidence.`actual_spans = <span count>`,
evidence.`min_required = config.min_spans_per_trace`).

## 4. orphan_span — `reason = "orphan_span"`

A span is an orphan if its `parent_span_id` is non-null but no span in
the same trace has that `span_id`. The check fails if the trace
contains at least one orphan. When this fires, the decision is
`config.orphan_action`; one `D_ORPHAN_SPAN` diagnostic is emitted per
orphan span (span_id is the orphan's id,
evidence.`missing_parent_span_id` is the dangling parent_span_id).

## Notes on co-emission

`D_FUTURE_TIMESTAMP` is independent of the precedence chain and is
emitted on every offending span regardless of which validation check
(if any) fired first. The other four checks compete for decision
ownership but each still emits its diagnostic if it observed its
condition.

Concretely: a trace that has both a cycle and two orphan spans gets
- one `D_CYCLE_DETECTED` and
- two `D_ORPHAN_SPAN` diagnostics,
and the decision uses `config.cycle_action` because cycle wins
precedence.
