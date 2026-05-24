'use strict';

// Report assembly and JSON output.

/**
 * Build the final report object from computed data.
 * @param {Object} params
 * @returns {Object}
 */
function buildReport(params) {
  // TODO
  return {};
}

/**
 * Deep-sort all object keys alphabetically at every nesting level.
 * @param {*} obj
 * @returns {*}
 */
function sortKeysDeep(obj) {
  if (Array.isArray(obj)) return obj.map(sortKeysDeep);
  if (obj !== null && typeof obj === 'object') {
    const sorted = {};
    for (const key of Object.keys(obj).sort()) {
      sorted[key] = sortKeysDeep(obj[key]);
    }
    return sorted;
  }
  return obj;
}

module.exports = { buildReport, sortKeysDeep };
