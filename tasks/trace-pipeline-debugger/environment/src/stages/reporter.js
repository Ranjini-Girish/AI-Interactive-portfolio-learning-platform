'use strict';

const { hashString } = require('../utils/hash');

function buildResults(traces, metricsResult, anomalies, spans, config, ctx) {
    const precision = config.output.precision;

    const traceSummary = {
        total_traces: traces.length,
        complete_traces: traces.filter(t => t.root_span !== null).length,
        incomplete_traces: traces.filter(t => t.root_span === null).length,
        avg_spans_per_trace: traces.length > 0
            ? parseFloat(
                (traces.reduce((sum, t) => sum + t.span_count, 0) / traces.length)
                    .toFixed(precision)
              )
            : 0
    };

    const edgeMap = {};
    for (const trace of traces) {
        for (const span of trace.spans) {
            if (span.parent_span_id) {
                const parent = trace.spans.find(
                    s => s.span_id === span.parent_span_id
                );
                if (parent && parent.service !== span.service) {
                    const key = `${parent.service}|${span.service}`;
                    edgeMap[key] = (edgeMap[key] || 0) + 1;
                }
            }
        }
    }

    const dependencyGraph = Object.entries(edgeMap)
        .map(([key, count]) => {
            const [source, target] = key.split('|');
            return { source, target, call_count: count };
        })
        .sort((a, b) =>
            a.source.localeCompare(b.source) || a.target.localeCompare(b.target)
        );

    return {
        trace_summary: traceSummary,
        service_stats: metricsResult,
        dependency_graph: dependencyGraph,
        anomalies
    };
}

function computeReportHash(report) {
    return 'sha256:' + hashString(JSON.stringify(report));
}

module.exports = { buildResults, computeReportHash };
