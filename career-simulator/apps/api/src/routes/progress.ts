import { Router } from 'express';
import { requireAuth } from '../middleware/auth';
import { buildProgressDashboard } from '../services/progress-dashboard';

export const progressRouter = Router();

progressRouter.use(requireAuth);

progressRouter.get('/dashboard', async (req, res) => {
  try {
    const dashboard = await buildProgressDashboard(req.user!.id, req.user!.fullName);
    res.json(dashboard);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Dashboard unavailable';
    res.status(503).json({ error: message, code: 'DB_UNAVAILABLE' });
  }
});
