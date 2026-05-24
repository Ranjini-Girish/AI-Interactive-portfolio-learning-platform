'use strict';

function durationMs(startIso, endIso) {
    const startMs = Date.parse(startIso);
    const endMs = Date.parse(endIso);
    return (endMs - startMs) / 1000;
}

function parseTimestamp(isoString) {
    return Date.parse(isoString);
}

function formatTimestamp(epochMs) {
    return new Date(epochMs).toISOString();
}

module.exports = { durationMs, parseTimestamp, formatTimestamp };
