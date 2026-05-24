export function sortedKeys(obj) {
  const result = {};
  for (const key of Object.keys(obj).sort()) {
    result[key] = obj[key];
  }
  return result;
}

export function groupBy(arr, keyFn) {
  const groups = {};
  for (const item of arr) {
    const key = keyFn(item);
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  }
  return groups;
}

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}
