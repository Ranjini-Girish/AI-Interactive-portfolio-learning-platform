import { DEBUG } from './constants';
export function deprecatedHelper() { return DEBUG ? 'debug' : 'prod'; }
export function legacyFormat(s) { return s.trim().toLowerCase(); }
