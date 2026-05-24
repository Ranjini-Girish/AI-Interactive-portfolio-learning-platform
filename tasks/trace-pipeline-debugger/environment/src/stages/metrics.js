'use strict';

const stats = require('../utils/stats');

function process(serviceStats, config, ctx) {
    const precision = config.output.precision;
    const percentiles = config.metrics.percentiles;

    const result = {};

    for (const [service, data] of Object.entries(serviceStats)) {
        const latencyStats = {};

        if (data.latencies.length > 0) {
            latencyStats.mean = parseFloat(stats.mean(data.latencies).toFixed(precision));
            latencyStats.min = Math.min(...data.latencies);
            latencyStats.max = Math.max(...data.latencies);

            for (const p of percentiles) {
                latencyStats[`p${p}`] = stats.percentile(data.latencies, p);
            }
        }

        const errorRate = data.count > 0
            ? parseFloat((data.error_count / data.count).toFixed(precision))
            : 0;

        result[service] = {
            span_count: data.count,
            error_count: data.error_count,
            error_rate: errorRate,
            latency: latencyStats
        };
    }

    ctx.metricsResult = result;
    return result;
}

module.exports = { process };
