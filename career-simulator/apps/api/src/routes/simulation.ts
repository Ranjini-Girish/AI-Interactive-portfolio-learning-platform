import { Router } from 'express';
import { z } from 'zod';
import { requireAuth } from '../middleware/auth';
import {
  getSimulationFixtures,
  getSimulationModule,
  listSimulationModules,
} from '../data/simulations';
import {
  countCompletedTasks,
  getSessionForUser,
  listSessionsForUser,
  saveSubmission,
  startSession,
} from '../repositories/simulation-repository';
import { gradeTaskSubmission } from '../services/simulation-grader';

const roleSchema = z.enum(['qa_tester', 'data_analyst', 'project_manager', 'ai_reviewer']);

const submitSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('written'), text: z.string().min(20) }),
  z.object({ kind: z.literal('test_cases'), text: z.string().min(40) }),
  z.object({
    kind: z.literal('bug_report'),
    title: z.string().min(5),
    severity: z.string().min(3),
    steps: z.string().min(20),
    expected: z.string().min(10),
    actual: z.string().min(10),
  }),
  z.object({ kind: z.literal('prioritize'), order: z.array(z.string()).min(4) }),
  z.object({
    kind: z.literal('review'),
    ratings: z.record(z.coerce.number().min(1).max(5)),
    feedback: z.string().min(20),
  }),
]);

export const simulationRouter = Router();

simulationRouter.get('/modules', requireAuth, async (req, res) => {
  const modules = listSimulationModules();
  const sessions = await listSessionsForUser(req.user!.id);
  const byRole = new Map(sessions.map((s) => [s.roleId, s]));

  res.json({
    modules: modules.map((m) => ({
      ...m,
      session: byRole.get(m.roleId) ?? null,
    })),
  });
});

simulationRouter.get('/modules/:roleId', requireAuth, (req, res) => {
  const parsed = roleSchema.safeParse(req.params.roleId);
  if (!parsed.success) {
    res.status(404).json({ error: 'Module not found', code: 'NOT_FOUND' });
    return;
  }

  const mod = getSimulationModule(parsed.data);
  if (!mod) {
    res.status(404).json({ error: 'Module not found', code: 'NOT_FOUND' });
    return;
  }

  res.json({ module: mod });
});

simulationRouter.get('/sessions/:roleId', requireAuth, async (req, res) => {
  const parsed = roleSchema.safeParse(req.params.roleId);
  if (!parsed.success) {
    res.status(400).json({ error: 'Invalid role', code: 'VALIDATION_ERROR' });
    return;
  }

  const session = await getSessionForUser(req.user!.id, parsed.data);
  if (!session) {
    res.status(404).json({ error: 'No session yet — start the module first', code: 'NOT_FOUND' });
    return;
  }

  res.json({ session });
});

simulationRouter.post('/sessions/:roleId/start', requireAuth, async (req, res) => {
  const parsed = roleSchema.safeParse(req.params.roleId);
  if (!parsed.success) {
    res.status(400).json({ error: 'Invalid role', code: 'VALIDATION_ERROR' });
    return;
  }

  if (!getSimulationModule(parsed.data)) {
    res.status(404).json({ error: 'Module not found', code: 'NOT_FOUND' });
    return;
  }

  try {
    const session = await startSession(req.user!.id, parsed.data);
    res.status(201).json({ session });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Could not start session';
    res.status(503).json({ error: message, code: 'DB_UNAVAILABLE' });
  }
});

simulationRouter.get('/tasks/:roleId/:taskId/fixtures', requireAuth, (req, res) => {
  const roleParsed = roleSchema.safeParse(req.params.roleId);
  if (!roleParsed.success) {
    res.status(404).json({ error: 'Not found', code: 'NOT_FOUND' });
    return;
  }

  const mod = getSimulationModule(roleParsed.data);
  const taskId = String(req.params.taskId);
  const task = mod?.tasks.find((t) => t.id === taskId);
  if (!task) {
    res.status(404).json({ error: 'Task not found', code: 'NOT_FOUND' });
    return;
  }

  res.json({
    task,
    fixtures: getSimulationFixtures(roleParsed.data, taskId),
  });
});

simulationRouter.post('/tasks/:roleId/:taskId/submit', requireAuth, async (req, res) => {
  const roleParsed = roleSchema.safeParse(req.params.roleId);
  if (!roleParsed.success) {
    res.status(400).json({ error: 'Invalid role', code: 'VALIDATION_ERROR' });
    return;
  }

  const taskId = String(req.params.taskId);
  const mod = getSimulationModule(roleParsed.data);
  const task = mod?.tasks.find((t) => t.id === taskId);
  if (!task) {
    res.status(404).json({ error: 'Task not found', code: 'NOT_FOUND' });
    return;
  }

  const bodyParsed = submitSchema.safeParse(req.body);
  if (!bodyParsed.success) {
    res.status(400).json({
      error: bodyParsed.error.errors[0]?.message ?? 'Invalid submission',
      code: 'VALIDATION_ERROR',
    });
    return;
  }

  const session = await getSessionForUser(req.user!.id, roleParsed.data);
  if (!session) {
    res.status(400).json({ error: 'Start the module before submitting tasks', code: 'NO_SESSION' });
    return;
  }

  const taskProgress = session.tasks.find((t) => t.taskId === task.id);
  if (taskProgress?.status === 'locked') {
    res.status(400).json({ error: 'Complete the previous task first', code: 'TASK_LOCKED' });
    return;
  }

  const grade = gradeTaskSubmission(roleParsed.data, task.id, bodyParsed.data);

  try {
    const updated = await saveSubmission({
      userId: req.user!.id,
      roleId: roleParsed.data,
      taskId: task.id,
      payload: bodyParsed.data,
      score: grade.score,
      passed: grade.passed,
      feedback: grade.feedback,
    });

    res.json({ grade, session: updated });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Submit failed';
    res.status(503).json({ error: message, code: 'DB_UNAVAILABLE' });
  }
});

simulationRouter.get('/stats', requireAuth, async (req, res) => {
  const completed = await countCompletedTasks(req.user!.id);
  const sessions = await listSessionsForUser(req.user!.id);
  res.json({
    tasksCompleted: completed,
    modulesStarted: sessions.length,
    modulesCompleted: sessions.filter((s) => s.status === 'completed').length,
  });
});
