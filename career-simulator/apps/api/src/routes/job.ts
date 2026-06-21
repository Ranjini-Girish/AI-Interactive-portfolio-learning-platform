import { Router } from 'express';
import { z } from 'zod';
import { getJobSampleById, listJobSampleMeta } from '../data/samples/jobs';
import { requireAuth } from '../middleware/auth';
import { getAnalysisById, getLatestAnalysis } from '../repositories/resume-repository';
import { getJobMatchById, getLatestJobMatch, saveJobMatch } from '../repositories/job-repository';
import { matchJobToResume } from '../services/jd-matcher';

const matchSchema = z.object({
  jdText: z.string().min(60, 'Paste the full job description'),
  targetRole: z.enum(['qa_tester', 'data_analyst', 'project_manager', 'ai_reviewer']).optional(),
  resumeAnalysisId: z.string().uuid().optional(),
});

const matchSampleSchema = z.object({
  sampleId: z.string().min(1),
  targetRole: z.enum(['qa_tester', 'data_analyst', 'project_manager', 'ai_reviewer']).optional(),
  resumeAnalysisId: z.string().uuid().optional(),
});

export const jobRouter = Router();

jobRouter.get('/samples', (_req, res) => {
  res.json({ samples: listJobSampleMeta() });
});

jobRouter.use(requireAuth);

async function resolveResume(userId: string, resumeAnalysisId?: string) {
  if (resumeAnalysisId) {
    const record = await getAnalysisById(userId, resumeAnalysisId);
    if (!record) return null;
    return record;
  }
  return getLatestAnalysis(userId);
}

jobRouter.get('/latest', async (req, res) => {
  const record = await getLatestJobMatch(req.user!.id);
  if (!record) {
    res.status(404).json({ error: 'No job match yet', code: 'NOT_FOUND' });
    return;
  }
  res.json(record);
});

jobRouter.get('/:id', async (req, res) => {
  const record = await getJobMatchById(req.user!.id, req.params.id);
  if (!record) {
    res.status(404).json({ error: 'Match not found', code: 'NOT_FOUND' });
    return;
  }
  res.json(record);
});

jobRouter.post('/match', async (req, res) => {
  const parsed = matchSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: parsed.error.errors[0]?.message ?? 'Invalid input',
      code: 'VALIDATION_ERROR',
    });
    return;
  }

  const resume = await resolveResume(req.user!.id, parsed.data.resumeAnalysisId);
  if (!resume) {
    res.status(400).json({
      error: 'Upload or analyze a resume first (Phase 3)',
      code: 'NO_RESUME',
    });
    return;
  }

  try {
    const analysis = matchJobToResume(
      parsed.data.jdText,
      resume.analysis,
      parsed.data.targetRole,
    );
    const record = await saveJobMatch({
      userId: req.user!.id,
      resumeAnalysisId: resume.id,
      sourceType: 'paste',
      jobTitle: analysis.jobTitle,
      rawJd: parsed.data.jdText,
      analysis,
    });
    res.status(201).json(record);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Match failed';
    res.status(400).json({ error: message, code: 'MATCH_ERROR' });
  }
});

jobRouter.post('/match-sample', async (req, res) => {
  const parsed = matchSampleSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: parsed.error.errors[0]?.message ?? 'Invalid input',
      code: 'VALIDATION_ERROR',
    });
    return;
  }

  const sample = getJobSampleById(parsed.data.sampleId);
  if (!sample) {
    res.status(404).json({ error: 'Sample JD not found', code: 'NOT_FOUND' });
    return;
  }

  const resume = await resolveResume(req.user!.id, parsed.data.resumeAnalysisId);
  if (!resume) {
    res.status(400).json({
      error: 'Upload or analyze a resume first (Phase 3)',
      code: 'NO_RESUME',
    });
    return;
  }

  try {
    const analysis = matchJobToResume(
      sample.text,
      resume.analysis,
      parsed.data.targetRole,
    );
    const record = await saveJobMatch({
      userId: req.user!.id,
      resumeAnalysisId: resume.id,
      sourceType: 'sample',
      sampleId: sample.id,
      jobTitle: analysis.jobTitle,
      rawJd: sample.text,
      analysis,
    });
    res.status(201).json(record);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Match failed';
    res.status(400).json({ error: message, code: 'MATCH_ERROR' });
  }
});
