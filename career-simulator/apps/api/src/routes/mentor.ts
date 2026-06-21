import { Router } from 'express';
import { z } from 'zod';
import { requireAuth } from '../middleware/auth';
import {
  appendMentorMessage,
  clearMentorHistory,
  getMentorHistory,
} from '../repositories/mentor-repository';
import {
  getMentorModel,
  isMentorConfigured,
  localMentorReply,
  streamMentorReply,
} from '../services/mentor-chat';
import { getLatestAnalysis } from '../repositories/resume-repository';

const chatSchema = z.object({
  message: z.string().min(1).max(4000),
  clearHistory: z.boolean().optional(),
});

export const mentorRouter = Router();

mentorRouter.get('/status', requireAuth, (_req, res) => {
  const configured = isMentorConfigured();
  res.json({
    configured,
    model: getMentorModel(),
    message: configured
      ? 'OpenAI mentor ready'
      : 'Set OPENAI_API_KEY in .env for live AI (local fallback active)',
  });
});

mentorRouter.get('/history', requireAuth, async (req, res) => {
  const messages = await getMentorHistory(req.user!.id);
  res.json({ messages });
});

mentorRouter.delete('/history', requireAuth, async (req, res) => {
  await clearMentorHistory(req.user!.id);
  res.json({ ok: true });
});

mentorRouter.post('/chat/stream', requireAuth, async (req, res) => {
  const parsed = chatSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: 'Invalid message', code: 'VALIDATION_ERROR' });
    return;
  }

  const userId = req.user!.id;
  const { message, clearHistory } = parsed.data;

  if (clearHistory) await clearMentorHistory(userId);

  const history = clearHistory ? [] : await getMentorHistory(userId);

  res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
  res.setHeader('Cache-Control', 'no-cache, no-transform');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders?.();

  const send = (payload: object) => {
    res.write(`data: ${JSON.stringify(payload)}\n\n`);
  };

  try {
    await appendMentorMessage(userId, 'user', message);

    if (!isMentorConfigured()) {
      const resume = await getLatestAnalysis(userId);
      const reply = localMentorReply(message, Boolean(resume));
      send({ content: reply, provider: 'local' });
      await appendMentorMessage(userId, 'assistant', reply);
      send({ done: true });
      res.end();
      return;
    }

    send({ provider: 'openai', model: getMentorModel() });

    const full = await streamMentorReply(userId, message, history, (chunk) => {
      send({ content: chunk });
    });

    await appendMentorMessage(userId, 'assistant', full);
    send({ done: true });
    res.end();
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Mentor error';
    send({ error: msg });
    res.end();
  }
});
