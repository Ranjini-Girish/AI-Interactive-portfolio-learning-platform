import { authenticate, authorize } from '../auth';
import { query } from '../db';
import { Logger } from '../logger';
export function handleUser(req) { authenticate(); return query('SELECT * FROM users'); }
export function getUser(id) { return query(`SELECT * FROM users WHERE id=${id}`); }
