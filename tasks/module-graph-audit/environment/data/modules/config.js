import {
  ENV_DEFAULTS,
  MAX_CONNECTIONS
} from './constants.js';

export function loadConfig() {
  return {
    ...ENV_DEFAULTS,
    maxConnections: MAX_CONNECTIONS,
    port: parseInt(process.env.PORT || '3000', 10),
    host: process.env.HOST || 'localhost',
  };
}

export function validateConfig(cfg) {
  if (!cfg.port || cfg.port < 1 || cfg.port > 65535) {
    throw new Error('Invalid port');
  }
  return true;
}

export default {
  port: 3000,
  host: 'localhost',
  debug: false,
};
