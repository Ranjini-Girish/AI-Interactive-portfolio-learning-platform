'use strict';

// Shared utility helpers.

/**
 * Round a number to N decimal places.
 * @param {number} value
 * @param {number} decimals
 * @returns {number}
 */
function roundN(value, decimals) {
  if (value === null || value === undefined) return value;
  const factor = Math.pow(10, decimals);
  return Math.round(value * factor) / factor;
}

/**
 * Parse an ISO 8601 timestamp to a Date object.
 * @param {string} iso
 * @returns {Date}
 */
function parseTimestamp(iso) {
  return new Date(iso);
}

/**
 * Compute the difference in fractional days between two dates.
 * @param {Date} a
 * @param {Date} b
 * @returns {number}
 */
function daysBetween(a, b) {
  return (a.getTime() - b.getTime()) / (1000 * 60 * 60 * 24);
}

module.exports = { roundN, parseTimestamp, daysBetween };
