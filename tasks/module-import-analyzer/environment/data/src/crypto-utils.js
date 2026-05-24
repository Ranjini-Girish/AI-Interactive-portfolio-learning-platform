import { SECRET_KEY, HASH_ALGORITHM } from './constants';
export function hashPassword(pw) { return SECRET_KEY + pw; }
export function verifyToken(tok) { return tok.startsWith(HASH_ALGORITHM); }
export function generateSalt() { return Math.random().toString(36); }
