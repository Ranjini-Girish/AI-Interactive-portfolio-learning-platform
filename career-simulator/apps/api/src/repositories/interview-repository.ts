import type {
  InterviewAnswerFeedback,
  InterviewMode,
  InterviewQuestion,
  InterviewResponseRecord,
  InterviewSessionRecord,
  InterviewSessionSummary,
  SimRole,
} from '@career-sim/shared';
import { getQuestionById, pickInterviewQuestions } from '../data/interviews/questions';
import { getPool } from '../db/pool';
import { buildImprovementSummary } from '../services/interview-grader';

type SessionRow = {
  id: string;
  role_id: SimRole;
  interview_type: InterviewMode;
  status: 'in_progress' | 'completed';
  overall_score: number | null;
  questions_total: number;
  question_ids: string[];
  improvement_summary: string[];
  created_at: Date;
  completed_at: Date | null;
};

type ResponseRow = {
  question_id: string;
  question_type: string;
  question_text: string;
  answer_text: string;
  score: number;
  feedback: InterviewAnswerFeedback;
  submitted_at: Date;
};

function pendingQuestions(questionIds: string[], responses: ResponseRow[], roleId: SimRole): InterviewQuestion[] {
  const answered = new Set(responses.map((r) => r.question_id));
  return questionIds
    .filter((id) => !answered.has(id))
    .map((id) => getQuestionById(id, roleId))
    .filter((q): q is InterviewQuestion => q !== null);
}

function toSessionRecord(row: SessionRow, responses: ResponseRow[]): InterviewSessionRecord {
  const mapped: InterviewResponseRecord[] = responses.map((r) => ({
    questionId: r.question_id,
    questionType: r.question_type as InterviewResponseRecord['questionType'],
    questionText: r.question_text,
    answerText: r.answer_text,
    score: r.score,
    feedback: r.feedback,
    submittedAt: r.submitted_at.toISOString(),
  }));

  return {
    id: row.id,
    roleId: row.role_id,
    interviewType: row.interview_type,
    status: row.status,
    overallScore: row.overall_score,
    questionsTotal: row.questions_total,
    questionsAnswered: responses.length,
    improvementSummary: row.improvement_summary ?? [],
    createdAt: row.created_at.toISOString(),
    completedAt: row.completed_at?.toISOString() ?? null,
    responses: mapped,
    pendingQuestions: pendingQuestions(row.question_ids, responses, row.role_id),
  };
}

async function loadResponses(sessionId: string): Promise<ResponseRow[]> {
  const pool = getPool();
  if (!pool) return [];

  const { rows } = await pool.query<ResponseRow>(
    `SELECT question_id, question_type, question_text, answer_text, score, feedback, submitted_at
     FROM interview_responses WHERE session_id = $1 ORDER BY submitted_at ASC`,
    [sessionId],
  );
  return rows;
}

export async function createInterviewSession(
  userId: string,
  roleId: SimRole,
  interviewType: InterviewMode,
): Promise<InterviewSessionRecord> {
  const pool = getPool();
  if (!pool) throw new Error('DATABASE_URL not configured');

  const questions = pickInterviewQuestions(roleId, interviewType);
  const questionIds = questions.map((q) => q.id);

  const { rows } = await pool.query<SessionRow>(
    `INSERT INTO interview_sessions (user_id, role_id, interview_type, questions_total, question_ids)
     VALUES ($1, $2, $3, $4, $5)
     RETURNING id, role_id, interview_type, status, overall_score, questions_total, question_ids, improvement_summary, created_at, completed_at`,
    [userId, roleId, interviewType, questionIds.length, JSON.stringify(questionIds)],
  );

  const row = rows[0];
  if (!row) throw new Error('Failed to create interview session');

  return toSessionRecord(row, []);
}

export async function getInterviewSession(
  userId: string,
  sessionId: string,
): Promise<InterviewSessionRecord | null> {
  const pool = getPool();
  if (!pool) return null;

  const { rows } = await pool.query<SessionRow>(
    `SELECT id, role_id, interview_type, status, overall_score, questions_total, question_ids, improvement_summary, created_at, completed_at
     FROM interview_sessions WHERE id = $1 AND user_id = $2 LIMIT 1`,
    [sessionId, userId],
  );

  const row = rows[0];
  if (!row) return null;

  const responses = await loadResponses(sessionId);
  return toSessionRecord(row, responses);
}

export async function listInterviewSessions(userId: string): Promise<InterviewSessionSummary[]> {
  const pool = getPool();
  if (!pool) return [];

  const { rows } = await pool.query<SessionRow & { answered: string }>(
    `SELECT s.id, s.role_id, s.interview_type, s.status, s.overall_score, s.questions_total, s.question_ids, s.improvement_summary, s.created_at, s.completed_at,
            (SELECT COUNT(*)::text FROM interview_responses r WHERE r.session_id = s.id) AS answered
     FROM interview_sessions s
     WHERE s.user_id = $1
     ORDER BY s.created_at DESC
     LIMIT 20`,
    [userId],
  );

  return rows.map((row) => ({
    id: row.id,
    roleId: row.role_id,
    interviewType: row.interview_type,
    status: row.status,
    overallScore: row.overall_score,
    questionsAnswered: parseInt(row.answered, 10),
    questionsTotal: row.questions_total,
    createdAt: row.created_at.toISOString(),
  }));
}

export async function saveInterviewResponse(input: {
  userId: string;
  sessionId: string;
  questionId: string;
  questionType: string;
  questionText: string;
  answerText: string;
  score: number;
  feedback: InterviewAnswerFeedback;
}): Promise<InterviewSessionRecord> {
  const pool = getPool();
  if (!pool) throw new Error('DATABASE_URL not configured');

  const session = await getInterviewSession(input.userId, input.sessionId);
  if (!session) throw new Error('Session not found');
  if (session.status === 'completed') throw new Error('Interview already completed');

  const allowedIds = new Set([
    ...session.responses.map((r) => r.questionId),
    ...session.pendingQuestions.map((q) => q.id),
  ]);
  if (!allowedIds.has(input.questionId)) {
    throw new Error('Question not in this session');
  }

  await pool.query(
    `INSERT INTO interview_responses (session_id, question_id, question_type, question_text, answer_text, score, feedback)
     VALUES ($1, $2, $3, $4, $5, $6, $7)
     ON CONFLICT (session_id, question_id) DO UPDATE SET
       answer_text = EXCLUDED.answer_text,
       score = EXCLUDED.score,
       feedback = EXCLUDED.feedback,
       submitted_at = NOW()`,
    [
      input.sessionId,
      input.questionId,
      input.questionType,
      input.questionText,
      input.answerText,
      input.score,
      JSON.stringify(input.feedback),
    ],
  );

  const updated = await getInterviewSession(input.userId, input.sessionId);
  if (!updated) throw new Error('Session missing after save');

  if (updated.pendingQuestions.length === 0) {
    const scores = updated.responses.map((r) => r.score);
    const overall = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
    const allImprovements = updated.responses.flatMap((r) => r.feedback.improvements);
    const summary = buildImprovementSummary(scores, allImprovements);

    await pool.query(
      `UPDATE interview_sessions SET status = 'completed', overall_score = $1, improvement_summary = $2, completed_at = NOW() WHERE id = $3`,
      [overall, JSON.stringify(summary), input.sessionId],
    );

    updated.status = 'completed';
    updated.overallScore = overall;
    updated.improvementSummary = summary;
    updated.completedAt = new Date().toISOString();
  }

  return updated;
}
