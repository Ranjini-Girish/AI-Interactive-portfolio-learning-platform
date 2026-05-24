import { getConnection } from './db.js';
import { loadConfig } from './config.js';
import { rateLimiter } from './middleware.js';

export function authenticate(req) {
  const token = req.headers?.authorization?.split(' ')[1];
  if (!token) throw new Error('No token');
  return verifyToken(token);
}

export function getSession(sessionId) {
  const conn = getConnection();
  return conn.query('SELECT * FROM sessions WHERE id = ?', [sessionId]);
}

export function createToken(user) {
  const cfg = loadConfig();
  return `${user.id}.${Date.now()}.${cfg.secret || 'default'}`;
}

function verifyToken(token) {
  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('Invalid token');
  return { userId: parts[0], iat: parseInt(parts[1], 10) };
}
