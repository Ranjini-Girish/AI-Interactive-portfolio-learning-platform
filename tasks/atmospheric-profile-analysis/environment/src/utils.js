/**
 * Utility functions for rounding, sorting, and interpolation.
 */

function roundTo(x, decimals) {
  if (x === null || x === undefined) return null;
  const f = Math.pow(10, decimals);
  return Math.round(x * f) / f;
}

function logInterp(pTarget, p1, p2, v1, v2) {
  // TODO: Implement log-linear pressure interpolation
  return v1;
}

module.exports = { roundTo, logInterp };
