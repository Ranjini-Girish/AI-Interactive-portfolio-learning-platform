'use strict';

const { validate, normalize } = require('../models/span');

function process(spans, config, ctx) {
    const results = [];
    for (const span of spans) {
        if (!validate(span)) {
            ctx.warn(`Invalid span skipped: ${span.span_id || 'unknown'}`);
            continue;
        }
        results.push(normalize(span));
    }
    return results;
}

module.exports = { process };
