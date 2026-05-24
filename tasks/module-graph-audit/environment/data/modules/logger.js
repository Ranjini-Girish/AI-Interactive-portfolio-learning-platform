import { loadConfig } from './config.js';
import { EventBus } from './events.js';

export function createLogger(config) {
  const cfg = config || loadConfig();
  const bus = new EventBus();
  return {
    level: cfg.debug ? 'debug' : 'info',
    log: (lvl, msg) => {
      bus.emit('log', { level: lvl, message: msg });
      log(lvl, msg);
    },
  };
}

export function log(level, message) {
  const ts = new Date().toISOString();
  console.log(`[${ts}] ${level}: ${message}`);
}

export const LOG_LEVELS = ['debug', 'info', 'warn', 'error'];
