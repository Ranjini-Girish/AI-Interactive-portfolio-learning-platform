'use strict';

const LEVEL_ORDER = { debug: 0, info: 1, warn: 2, error: 3 };

function meetsMinLevel(spanLevel, minLevel) {
    return spanLevel >= minLevel;
}

function process(spans, config, ctx) {
    const minLevel = config.filter.min_level;
    const excludeServices = new Set(config.filter.exclude_services || []);

    return spans.filter(span => {
        if (excludeServices.has(span.service)) return false;
        return meetsMinLevel(span.level, minLevel);
    });
}

module.exports = { process };
