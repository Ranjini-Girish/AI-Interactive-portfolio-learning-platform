import { PATTERNS } from './constants';
export function formatLog(msg) { return `[LOG] ${msg}`; }
export function formatError(msg) { return `[ERR] ${msg}`; }
export function formatDate(d) { return d.toISOString(); }
