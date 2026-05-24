'use strict';

const parser = require('../stages/parser');
const filter = require('../stages/filter');
const correlator = require('../stages/correlator');
const aggregator = require('../stages/aggregator');
const metrics = require('../stages/metrics');
const anomaly = require('../stages/anomaly');
const reporter = require('../stages/reporter');
const Context = require('./context');

class PipelineEngine {
    constructor(config) {
        this.config = config;
    }

    run(spans) {
        const ctx = new Context(this.config);

        const parsed = parser.process(spans, this.config, ctx);
        const filtered = filter.process(parsed, this.config, ctx);
        const traces = correlator.process(filtered, this.config, ctx);
        const serviceStats = aggregator.process(filtered, this.config, ctx);
        const metricsResult = metrics.process(serviceStats, this.config, ctx);
        const anomalies = anomaly.process(filtered, metricsResult, this.config, ctx);
        const results = reporter.buildResults(
            traces, metricsResult, anomalies, filtered, this.config, ctx
        );

        return results;
    }
}

module.exports = PipelineEngine;
