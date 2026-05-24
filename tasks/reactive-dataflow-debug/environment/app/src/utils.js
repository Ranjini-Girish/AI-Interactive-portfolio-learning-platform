/**
 * Utility functions for the reactive dataflow engine.
 */

export function roundToFixed(value, precision) {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'number' || !isFinite(value)) return value;
  return parseFloat(value.toFixed(precision));
}

export function isValidCellId(id) {
  return /^[A-Z][A-Z0-9]*[0-9]+$/.test(id);
}

export function compareCellIds(a, b) {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

export function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}
