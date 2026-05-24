import { loadConfig } from './config.js';
import { createLogger } from './logger.js';

let pool = null;

export function getConnection() {
  if (!pool) {
    const cfg = loadConfig();
    const logger = createLogger(cfg);
    pool = new ConnectionPool(cfg.maxConnections, logger);
  }
  return pool;
}

export function query(sql, params = []) {
  const conn = getConnection();
  return conn.execute(sql, params);
}

export class ConnectionPool {
  constructor(maxSize, logger) {
    this.maxSize = maxSize;
    this.connections = [];
    this.logger = logger;
  }

  execute(sql, params) {
    this.logger.log('debug', `Executing: ${sql}`);
    return { rows: [], affectedRows: 0 };
  }

  close() {
    this.connections.forEach(c => c.end());
    this.connections = [];
  }
}
