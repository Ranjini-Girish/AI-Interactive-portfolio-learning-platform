import { authenticate, getSession } from './auth.js';
import { createLogger } from './logger.js';

export function applyMiddleware(app) {
  app.use = (mw) => { app.middleware = app.middleware || []; app.middleware.push(mw); };
  app.use(corsMiddleware());
  app.use(rateLimiter());
}

export function corsMiddleware() {
  return (req, res, next) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    next();
  };
}

export function rateLimiter(maxReqs = 100) {
  const counts = new Map();
  return (req, res, next) => {
    const ip = req.ip;
    const count = (counts.get(ip) || 0) + 1;
    counts.set(ip, count);
    if (count > maxReqs) {
      res.status(429).send('Too Many Requests');
      return;
    }
    next();
  };
}
