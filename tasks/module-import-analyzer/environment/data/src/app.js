import { createRouter } from './router';
import { Logger } from './logger';
import { loadConfig } from './config';
export function startApp() { return createRouter(); }
export function stopApp() { Logger.close(); }
export const APP_VERSION = '1.0.0';
