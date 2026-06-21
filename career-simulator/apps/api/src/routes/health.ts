import { Router } from 'express';
import type { HealthResponse } from '@career-sim/shared';
import { env } from '../config/env';
import { checkDatabase } from '../db/pool';
import { isMentorConfigured } from '../services/mentor-chat';

export const healthRouter = Router();

healthRouter.get('/health', async (_req, res) => {
  const database = await checkDatabase();
  const body: HealthResponse = {
    ok: database !== 'disconnected',
    service: 'career-simulator-api',
    phase: 10,
    timestamp: new Date().toISOString(),
    database,
    auth: database === 'connected' ? 'ready' : 'needs_database',
    mentor:
      database !== 'connected'
        ? 'needs_database'
        : isMentorConfigured()
          ? 'ready'
          : 'needs_openai_key',
    simulation: database === 'connected' ? 'ready' : 'needs_database',
    portfolio: database === 'connected' ? 'ready' : 'needs_database',
    interview: database === 'connected' ? 'ready' : 'needs_database',
    deploy: database === 'connected' ? 'production_ready' : 'needs_database',
  };
  res.json(body);
});

healthRouter.get('/', (_req, res) => {
  res.json({
    name: 'AI Career Transition & Real-World Experience Simulator API',
    phase: 10,
    environment: env.NODE_ENV,
    docs: '/api/health',
  });
});
