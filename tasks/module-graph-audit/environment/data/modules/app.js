import * as router from './router.js';
import { createLogger } from './logger.js';
import { applyMiddleware } from './middleware.js';

export function createApp(config) {
  const logger = createLogger(config);
  const app = { config, logger, routes: [] };
  applyMiddleware(app);
  router.defineRoutes(app);
  return app;
}

export function startApp(app) {
  app.running = true;
  return app;
}

export function stopApp(app) {
  app.running = false;
}
