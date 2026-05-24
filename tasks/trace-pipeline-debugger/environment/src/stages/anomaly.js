'use strict';

const stats = require('../utils/stats');
const time = require('../utils/time');

function process(spans, metricsResult, config, ctx) {
    const threshold = config.anomaly.threshold;
    const minSamples = config.anomaly.min_samples;
    const precision = config.output.precision;

    const anomalies = [];

    const byService = {};
    for (const span of spans) {
        if (!byService[span.service]) byService[span.service] = [];
        byService[span.service].push(span);
    }

    for (const [service, serviceSpans] of Object.entries(byService)) {
        if (serviceSpans.length < minSamples) continue;

        const latencies = serviceSpans.map(s =>
            time.durationMs(s.start_time, s.end_time)
        );
        const m = stats.mean(latencies);
        const sd = stats.stddev(latencies);

        if (sd === 0) continue;

        for (let i = 0; i < serviceSpans.length; i++) {
            const zScore = Math.abs((latencies[i] - m) / sd);
            if (zScore > threshold) {
                anomalies.push({
                    span_id: serviceSpans[i].span_id,
                    trace_id: serviceSpans[i].trace_id,
                    service,
                    latency_ms: parseFloat(latencies[i].toFixed(precision)),
                    z_score: parseFloat(zScore.toFixed(precision)),
                    threshold
                });
            }
        }
    }

    anomalies.sort((a, b) => b.z_score - a.z_score);
    ctx.anomalies = anomalies;
    return anomalies;
}

module.exports = { process };
