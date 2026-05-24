'use strict';

function roundTo(value, decimals) {
    const factor = Math.pow(10, decimals);
    return Math.round(value * factor) / factor;
}

function formatPercent(value, decimals) {
    return parseFloat((value * 100).toFixed(decimals));
}

module.exports = { roundTo, formatPercent };
