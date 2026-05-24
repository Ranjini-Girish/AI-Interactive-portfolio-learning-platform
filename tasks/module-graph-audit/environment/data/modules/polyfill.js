if (typeof globalThis.structuredClone === 'undefined') {
  globalThis.structuredClone = function structuredClone(obj) {
    return JSON.parse(JSON.stringify(obj));
  };
}

if (!Array.prototype.at) {
  Array.prototype.at = function at(index) {
    const len = this.length;
    const k = index >= 0 ? index : len + index;
    if (k < 0 || k >= len) return undefined;
    return this[k];
  };
}

if (!Object.hasOwn) {
  Object.hasOwn = function hasOwn(obj, prop) {
    return Object.prototype.hasOwnProperty.call(obj, prop);
  };
}
