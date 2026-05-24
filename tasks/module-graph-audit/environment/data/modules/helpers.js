import { MAX_RETRIES } from './constants.js';

export function retry(fn, attempts = MAX_RETRIES) {
  for (let i = 0; i < attempts; i++) {
    try { return fn(); }
    catch (e) { if (i === attempts - 1) throw e; }
  }
}

export function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

export function memoize(fn) {
  const cache = new Map();
  return (...args) => {
    const key = JSON.stringify(args);
    if (!cache.has(key)) cache.set(key, fn(...args));
    return cache.get(key);
  };
}

export default function identity(x) {
  return x;
}
