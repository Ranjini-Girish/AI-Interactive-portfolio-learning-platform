# Trace Correlation

## Grouping

Spans are grouped into traces by their `trace_id`. Each trace has exactly one root span (where `parent_span_id` is `null` or absent). If no root span exists for a trace, that trace is discarded.

## Time Window

After finding the root span, a correlation window is applied. The window extends from the root span's `start_time` to `start_time + window_ms` (inclusive on both ends). A span belongs to the trace if its `start_time` falls within `[root_start, root_start + window_ms]`.

Formally: `span.start_time >= root_start AND span.start_time <= root_start + window_ms`.

Spans whose `start_time` falls exactly on the window boundary (equal to `root_start + window_ms`) are included.

## Minimum Span Count

Traces with fewer than `config.correlator.min_spans_per_trace` spans (after window filtering) are discarded.

## Span Tree

Within each valid trace, spans are organized into a tree using `parent_span_id`. Each span node includes a `children` array of its direct child spans. The root span is the entry point of the tree.
