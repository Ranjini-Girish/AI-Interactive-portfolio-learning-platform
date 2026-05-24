'use strict';

const REQUIRED_FIELDS = ['span_id', 'trace_id', 'service', 'start_time', 'end_time'];

function validate(span) {
    for (const field of REQUIRED_FIELDS) {
        if (span[field] === undefined || span[field] === null) {
            return false;
        }
    }
    return true;
}

function normalize(span) {
    return {
        span_id: span.span_id,
        trace_id: span.trace_id,
        parent_span_id: span.parent_span_id || null,
        service: span.service,
        operation: span.operation || 'unknown',
        start_time: span.start_time,
        end_time: span.end_time,
        status: span.status || 'ok',
        level: span.level || 'info',
        tags: span.tags || {}
    };
}

module.exports = { validate, normalize };
