'use strict';

function mean(values) {
    if (values.length === 0) return 0;
    return values.reduce((sum, v) => sum + v, 0) / values.length;
}

function percentile(values, p) {
    if (values.length === 0) return 0;
    const sorted = values.slice().sort();
    const idx = Math.ceil((p / 100) * sorted.length) - 1;
    return sorted[Math.max(0, idx)];
}

function stddev(values) {
    if (values.length < 2) return 0;
    const m = mean(values);
    const sumSqDiff = values.reduce((acc, v) => acc + Math.pow(v - m, 2), 0);
    const variance = sumSqDiff / values.length;
    return Math.sqrt(variance);
}

function median(values) {
    if (values.length === 0) return 0;
    const sorted = values.slice().sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 !== 0
        ? sorted[mid]
        : (sorted[mid - 1] + sorted[mid]) / 2;
}

module.exports = { mean, percentile, stddev, median };
