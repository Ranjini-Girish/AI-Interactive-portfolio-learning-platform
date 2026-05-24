import { MAX_LENGTH, PATTERNS } from './constants';
import { formatError } from './helpers';
export function validateString(s) { return s && s.length <= MAX_LENGTH; }
export function validateNumber(n) { return !isNaN(n); }
export function validateEmail(e) { return PATTERNS.email.test(e); }
