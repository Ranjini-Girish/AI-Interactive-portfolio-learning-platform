'use strict';

const time = require('../utils/time');

function process(spans, config, ctx) {
    const template = {
        count: 0,
        error_count: 0,
        latencies: [],
        total_duration: 0
    };

    const services = [...new Set(spans.map(s => s.service))].sort();
    const stats = {};

    for (const service of services) {
        stats[service] = Object.assign({}, template);
    }

    for (const span of spans) {
        const svc = stats[span.service];
        if (!svc) continue;
        svc.count++;
        if (span.status === 'error' || span.level === 'error') {
            svc.error_count++;
        }
        const latency = time.durationMs(span.start_time, span.end_time);
        svc.latencies.push(latency);
        svc.total_duration += latency;
    }

    ctx.serviceStats = stats;
    return stats;
}

module.exports = { process };
