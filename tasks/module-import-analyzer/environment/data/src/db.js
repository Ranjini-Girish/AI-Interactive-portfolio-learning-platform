import { loadConfig } from './config';
import { Logger } from './logger';
export function query(sql) { Logger.info(sql); return []; }
export function transaction(fn) { return fn(); }
export function connect() { return loadConfig().host; }
