import { Router } from 'express';
import { z } from 'zod';
import { requireAuth } from '../middleware/auth';
import { AuthError, getUserById, loginUser, registerUser } from '../services/auth-service';
import { buildProgressDashboard } from '../services/progress-dashboard';

const registerSchema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  fullName: z.string().min(2, 'Full name is required').max(120),
});

const loginSchema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});

export const authRouter = Router();

authRouter.post('/register', async (req, res) => {
  const parsed = registerSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: parsed.error.errors[0]?.message ?? 'Invalid input',
      code: 'VALIDATION_ERROR',
    });
    return;
  }

  try {
    const result = await registerUser(parsed.data);
    res.status(201).json(result);
  } catch (err) {
    if (err instanceof AuthError) {
      res.status(err.statusCode).json({ error: err.message, code: err.code });
      return;
    }
    if (err instanceof Error && err.message.includes('DATABASE_URL')) {
      res.status(503).json({
        error: 'Database not configured. Set DATABASE_URL and run npm run db:up',
        code: 'DB_UNAVAILABLE',
      });
      return;
    }
    throw err;
  }
});

authRouter.post('/login', async (req, res) => {
  const parsed = loginSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: parsed.error.errors[0]?.message ?? 'Invalid input',
      code: 'VALIDATION_ERROR',
    });
    return;
  }

  try {
    const result = await loginUser(parsed.data);
    res.json(result);
  } catch (err) {
    if (err instanceof AuthError) {
      res.status(err.statusCode).json({ error: err.message, code: err.code });
      return;
    }
    res.status(503).json({
      error: 'Database not configured. Set DATABASE_URL and run npm run db:up',
      code: 'DB_UNAVAILABLE',
    });
  }
});

authRouter.get('/me', requireAuth, (req, res) => {
  res.json({ user: req.user });
});

/** Legacy dashboard alias — prefer GET /api/progress/dashboard */
authRouter.get('/dashboard', requireAuth, async (req, res) => {
  try {
    const dashboard = await buildProgressDashboard(req.user!.id, req.user!.fullName);
    res.json({
      message: dashboard.message,
      phase: dashboard.phase,
      nextStep: dashboard.nextSteps[0]?.description ?? 'Explore the platform',
      stats: {
        tasksCompleted: dashboard.stats.tasksCompleted,
        skillsLearned: dashboard.stats.skillsIdentified,
        jobReadinessScore: dashboard.readiness.score,
        projectsInProgress: dashboard.stats.modulesInProgress,
      },
      resume: dashboard.resume,
      jobMatch: dashboard.jobMatch,
      simulation: dashboard.activeSimulation
        ? {
            roleId: dashboard.activeSimulation.roleId,
            progressPercent: dashboard.activeSimulation.progressPercent,
            tasksCompleted: dashboard.activeSimulation.tasksCompleted,
            totalTasks: dashboard.activeSimulation.totalTasks,
          }
        : null,
      progress: dashboard,
    });
  } catch (err) {
    res.status(503).json({
      error: 'Database not configured. Set DATABASE_URL and run npm run db:up',
      code: 'DB_UNAVAILABLE',
    });
  }
});

/** Dev helper — verify token resolves to user */
authRouter.get('/verify', requireAuth, async (req, res) => {
  const user = await getUserById(req.user!.id);
  res.json({ valid: Boolean(user), user });
});
