import { authenticate } from './auth';
import { Logger } from './logger';
export function applyMiddleware() { authenticate(); Logger.info('mw'); }
export function corsMiddleware() { return { origin: '*' }; }
