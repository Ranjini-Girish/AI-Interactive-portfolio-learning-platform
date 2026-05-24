export const VERSION = '2.4.1';

export const MAX_RETRIES = 3;

export const MAX_CONNECTIONS = 10;

export const ENV_DEFAULTS = {
  NODE_ENV: 'development',
  LOG_LEVEL: 'info',
};

export const FIELD_LIMITS = {
  name: 100,
  email: 255,
  description: 1000,
};

export const PATTERNS = {
  email: /^[^@\s]+@[^@\s]+\.[^@\s]+$/,
  uuid: /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
};

export const API_PREFIX = '/api/v1';
