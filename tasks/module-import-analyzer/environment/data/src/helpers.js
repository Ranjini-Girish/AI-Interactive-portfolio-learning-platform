import { MAX_LENGTH } from './constants';
import { validateString } from './validators';
export function formatError(msg) { return `Error: ${msg}`; }
export function deepMerge(a, b) { return Object.assign({}, a, b); }
export function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
