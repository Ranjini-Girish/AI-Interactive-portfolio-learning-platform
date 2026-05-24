'use strict';

class Context {
    constructor(config) {
        this.config = config;
        this.traces = [];
        this.serviceStats = {};
        this.metricsResult = {};
        this.anomalies = [];
        this.warnings = [];
    }

    warn(message) {
        this.warnings.push(message);
    }
}

module.exports = Context;
