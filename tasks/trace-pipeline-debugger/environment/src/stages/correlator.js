'use strict';

function process(spans, config, ctx) {
    const windowMs = config.correlator.window_ms;
    const minSpans = config.correlator.min_spans_per_trace;

    const traceMap = {};
    for (const span of spans) {
        if (!traceMap[span.trace_id]) {
            traceMap[span.trace_id] = [];
        }
        traceMap[span.trace_id].push(span);
    }

    const traces = [];
    for (const [traceId, traceSpans] of Object.entries(traceMap)) {
        const root = traceSpans.find(s => !s.parent_span_id);
        if (!root) continue;

        const rootStart = new Date(root.start_time).getTime();
        const windowEnd = rootStart + windowMs;

        const inWindow = traceSpans.filter(s => {
            const spanTime = new Date(s.start_time).getTime();
            return spanTime >= rootStart && spanTime < windowEnd;
        });

        if (inWindow.length >= minSpans) {
            const spanMap = {};
            for (const s of inWindow) {
                spanMap[s.span_id] = { ...s, children: [] };
            }
            for (const s of inWindow) {
                if (s.parent_span_id && spanMap[s.parent_span_id]) {
                    spanMap[s.parent_span_id].children.push(spanMap[s.span_id]);
                }
            }
            traces.push({
                trace_id: traceId,
                root_span: spanMap[root.span_id] || null,
                spans: inWindow,
                span_count: inWindow.length
            });
        }
    }

    ctx.traces = traces;
    return traces;
}

module.exports = { process };
