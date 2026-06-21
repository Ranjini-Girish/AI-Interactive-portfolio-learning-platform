import express from 'express';
import cors from 'cors';
import { env } from './config/env';
import { runMigrations } from './db/migrate';
import { apiRouter } from './routes';
import { errorHandler } from './middleware/error-handler';

const app = express();

app.set('trust proxy', 1);

app.use(
  cors({
    origin: env.CORS_ORIGIN.split(',').map((o) => o.trim()),
    credentials: true,
  }),
);
app.use(express.json({ limit: '2mb' }));

app.use('/api', apiRouter);

app.use(errorHandler);

async function start() {
  if (env.NODE_ENV === 'production' && env.JWT_SECRET.includes('change-me')) {
    console.warn('[api] WARNING: Set a strong JWT_SECRET in production');
  }

  await runMigrations();

  app.listen(env.PORT, () => {
    console.log(`[api] Phase 10 — listening on port ${env.PORT} (${env.NODE_ENV})`);
    console.log(`[api] Health: GET /api/health`);
    if (env.PUBLIC_API_URL) {
      console.log(`[api] Public URL: ${env.PUBLIC_API_URL}`);
    }
  });
}

start().catch((err) => {
  console.error('[api] Failed to start:', err);
  process.exit(1);
});
