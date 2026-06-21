import type {
  SimRole,
  SimTaskProgress,
  SimTaskStatus,
  SimulationSessionRecord,
} from '@career-sim/shared';
import { getSimulationModule } from '../data/simulations';
import { getPool } from '../db/pool';

type SessionRow = {
  id: string;
  role_id: SimRole;
  status: 'in_progress' | 'completed';
  started_at: Date;
  completed_at: Date | null;
};

type SubmissionRow = {
  task_id: string;
  score: number;
  passed: boolean;
  feedback: string[];
  submitted_at: Date;
};

function buildTaskProgress(
  roleId: SimRole,
  submissions: Map<string, SubmissionRow>,
): SimTaskProgress[] {
  const mod = getSimulationModule(roleId);
  if (!mod) return [];

  let unlocked = true;
  return mod.tasks.map((task) => {
    const sub = submissions.get(task.id);
    let status: SimTaskStatus;

    if (!unlocked) {
      status = 'locked';
    } else if (sub?.passed) {
      status = 'passed';
    } else if (sub) {
      status = 'needs_revision';
    } else {
      status = 'available';
    }

    if (!sub?.passed) unlocked = false;

    return {
      taskId: task.id,
      status,
      score: sub?.score ?? null,
      feedback: sub?.feedback ?? [],
      submittedAt: sub?.submitted_at.toISOString() ?? null,
    };
  });
}

function toSessionRecord(row: SessionRow, tasks: SimTaskProgress[]): SimulationSessionRecord {
  const passedCount = tasks.filter((t) => t.status === 'passed').length;
  const total = tasks.length;
  const progressPercent = total ? Math.round((passedCount / total) * 100) : 0;
  const status = passedCount === total && total > 0 ? 'completed' : row.status;

  return {
    id: row.id,
    roleId: row.role_id,
    status,
    progressPercent,
    tasksCompleted: passedCount,
    totalTasks: total,
    startedAt: row.started_at.toISOString(),
    completedAt: row.completed_at?.toISOString() ?? null,
    tasks,
  };
}

async function loadSubmissions(sessionId: string): Promise<Map<string, SubmissionRow>> {
  const pool = getPool();
  const map = new Map<string, SubmissionRow>();
  if (!pool) return map;

  const { rows } = await pool.query<SubmissionRow>(
    `SELECT task_id, score, passed, feedback, submitted_at
     FROM simulation_submissions WHERE session_id = $1`,
    [sessionId],
  );

  for (const row of rows) {
    map.set(row.task_id, row);
  }
  return map;
}

export async function getSessionForUser(
  userId: string,
  roleId: SimRole,
): Promise<SimulationSessionRecord | null> {
  const pool = getPool();
  if (!pool) return null;

  const { rows } = await pool.query<SessionRow>(
    `SELECT id, role_id, status, started_at, completed_at
     FROM simulation_sessions WHERE user_id = $1 AND role_id = $2 LIMIT 1`,
    [userId, roleId],
  );

  const row = rows[0];
  if (!row) return null;

  const subs = await loadSubmissions(row.id);
  const tasks = buildTaskProgress(roleId, subs);
  return toSessionRecord(row, tasks);
}

export async function listSessionsForUser(userId: string): Promise<SimulationSessionRecord[]> {
  const pool = getPool();
  if (!pool) return [];

  const { rows } = await pool.query<SessionRow>(
    `SELECT id, role_id, status, started_at, completed_at
     FROM simulation_sessions WHERE user_id = $1 ORDER BY started_at DESC`,
    [userId],
  );

  const sessions: SimulationSessionRecord[] = [];
  for (const row of rows) {
    const subs = await loadSubmissions(row.id);
    const tasks = buildTaskProgress(row.role_id, subs);
    sessions.push(toSessionRecord(row, tasks));
  }
  return sessions;
}

export async function startSession(userId: string, roleId: SimRole): Promise<SimulationSessionRecord> {
  const pool = getPool();
  if (!pool) throw new Error('DATABASE_URL not configured');

  const existing = await getSessionForUser(userId, roleId);
  if (existing) return existing;

  const mod = getSimulationModule(roleId);
  if (!mod) throw new Error('Unknown simulation role');

  const { rows } = await pool.query<SessionRow>(
    `INSERT INTO simulation_sessions (user_id, role_id)
     VALUES ($1, $2)
     RETURNING id, role_id, status, started_at, completed_at`,
    [userId, roleId],
  );

  const row = rows[0];
  if (!row) throw new Error('Failed to create session');

  const tasks = buildTaskProgress(roleId, new Map());
  return toSessionRecord(row, tasks);
}

export async function saveSubmission(input: {
  userId: string;
  roleId: SimRole;
  taskId: string;
  payload: unknown;
  score: number;
  passed: boolean;
  feedback: string[];
}): Promise<SimulationSessionRecord> {
  const pool = getPool();
  if (!pool) throw new Error('DATABASE_URL not configured');

  const session = await getSessionForUser(input.userId, input.roleId);
  if (!session) throw new Error('Start the simulation module first');

  await pool.query(
    `INSERT INTO simulation_submissions (session_id, task_id, payload, score, passed, feedback)
     VALUES ($1, $2, $3, $4, $5, $6)
     ON CONFLICT (session_id, task_id) DO UPDATE SET
       payload = EXCLUDED.payload,
       score = EXCLUDED.score,
       passed = EXCLUDED.passed,
       feedback = EXCLUDED.feedback,
       submitted_at = NOW()`,
    [
      session.id,
      input.taskId,
      JSON.stringify(input.payload),
      input.score,
      input.passed,
      JSON.stringify(input.feedback),
    ],
  );

  const updated = await getSessionForUser(input.userId, input.roleId);
  if (!updated) throw new Error('Session missing after submit');

  if (updated.status === 'completed') {
    await pool.query(
      `UPDATE simulation_sessions SET status = 'completed', completed_at = NOW() WHERE id = $1`,
      [session.id],
    );
    updated.status = 'completed';
    updated.completedAt = new Date().toISOString();
  }

  return updated;
}

export async function countCompletedTasks(userId: string): Promise<number> {
  const pool = getPool();
  if (!pool) return 0;

  const { rows } = await pool.query<{ count: string }>(
    `SELECT COUNT(*)::text AS count FROM simulation_submissions ss
     JOIN simulation_sessions s ON s.id = ss.session_id
     WHERE s.user_id = $1 AND ss.passed = TRUE`,
    [userId],
  );

  return parseInt(rows[0]?.count ?? '0', 10);
}
