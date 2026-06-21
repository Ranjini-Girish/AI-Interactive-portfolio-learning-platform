import { Router } from 'express';
import { z } from 'zod';
import { listQuestionPreview, getQuestionById } from '../data/interviews/questions';
import { requireAuth } from '../middleware/auth';
import { getLatestAnalysis } from '../repositories/resume-repository';
import {
  createInterviewSession,
  getInterviewSession,
  listInterviewSessions,
  saveInterviewResponse,
} from '../repositories/interview-repository';
import { gradeInterviewAnswer, isInterviewAiConfigured } from '../services/interview-grader';
import { getMentorModel } from '../services/mentor-prompt';

const roleSchema = z.enum(['qa_tester', 'data_analyst', 'project_manager', 'ai_reviewer']);
const modeSchema = z.enum(['behavioral', 'technical', 'mixed']);

const startSchema = z.object({
  roleId: roleSchema,
  interviewType: modeSchema,
});

const answerSchema = z.object({
  questionId: z.string().min(1),
  answer: z.string().min(30, 'Write at least a few sentences'),
});

export const interviewRouter = Router();

interviewRouter.use(requireAuth);

interviewRouter.get('/status', async (req, res) => {
  const resume = await getLatestAnalysis(req.user!.id);
  res.json({
    configured: isInterviewAiConfigured(),
    model: getMentorModel(),
    hasResume: Boolean(resume),
  });
});

interviewRouter.get('/sessions', async (req, res) => {
  const sessions = await listInterviewSessions(req.user!.id);
  res.json({ sessions });
});

interviewRouter.get('/preview/:roleId', (req, res) => {
  const parsed = roleSchema.safeParse(req.params.roleId);
  if (!parsed.success) {
    res.status(404).json({ error: 'Role not found', code: 'NOT_FOUND' });
    return;
  }
  res.json({ preview: listQuestionPreview(parsed.data) });
});

interviewRouter.post('/sessions', async (req, res) => {
  const parsed = startSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: parsed.error.errors[0]?.message ?? 'Invalid input',
      code: 'VALIDATION_ERROR',
    });
    return;
  }

  try {
    const session = await createInterviewSession(
      req.user!.id,
      parsed.data.roleId,
      parsed.data.interviewType,
    );
    res.status(201).json({ session });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Could not start interview';
    res.status(503).json({ error: message, code: 'DB_UNAVAILABLE' });
  }
});

interviewRouter.get('/sessions/:sessionId', async (req, res) => {
  const session = await getInterviewSession(req.user!.id, String(req.params.sessionId));
  if (!session) {
    res.status(404).json({ error: 'Session not found', code: 'NOT_FOUND' });
    return;
  }
  res.json({ session });
});

interviewRouter.post('/sessions/:sessionId/answer', async (req, res) => {
  const parsed = answerSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: parsed.error.errors[0]?.message ?? 'Invalid answer',
      code: 'VALIDATION_ERROR',
    });
    return;
  }

  const sessionId = String(req.params.sessionId);
  const session = await getInterviewSession(req.user!.id, sessionId);
  if (!session) {
    res.status(404).json({ error: 'Session not found', code: 'NOT_FOUND' });
    return;
  }

  const question = getQuestionById(parsed.data.questionId, session.roleId);
  if (!question) {
    res.status(404).json({ error: 'Question not found', code: 'NOT_FOUND' });
    return;
  }

  try {
    const feedback = await gradeInterviewAnswer({
      userId: req.user!.id,
      roleId: session.roleId,
      questionType: question.type,
      questionText: question.text,
      answer: parsed.data.answer,
    });

    const updated = await saveInterviewResponse({
      userId: req.user!.id,
      sessionId,
      questionId: question.id,
      questionType: question.type,
      questionText: question.text,
      answerText: parsed.data.answer,
      score: feedback.score,
      feedback,
    });

    res.json({ feedback, session: updated });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Submit failed';
    res.status(400).json({ error: message, code: 'SUBMIT_ERROR' });
  }
});
