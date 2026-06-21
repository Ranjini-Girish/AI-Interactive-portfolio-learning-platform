import { Router } from 'express';
import multer from 'multer';
import { z } from 'zod';
import { listSampleMeta, getSampleById } from '../data/samples';
import { requireAuth } from '../middleware/auth';
import {
  getAnalysisById,
  getLatestAnalysis,
  saveResumeAnalysis,
} from '../repositories/resume-repository';
import { analyzeResumeText } from '../services/resume-analyzer';
import { extractTextFromFile } from '../services/resume-parser';

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 5 * 1024 * 1024 },
});

const analyzeTextSchema = z.object({
  text: z.string().min(80, 'Paste at least a few resume sections'),
  targetRole: z.enum(['qa_tester', 'data_analyst', 'project_manager', 'ai_reviewer']).optional(),
});

const analyzeSampleSchema = z.object({
  sampleId: z.string().min(1),
  targetRole: z.enum(['qa_tester', 'data_analyst', 'project_manager', 'ai_reviewer']).optional(),
});

export const resumeRouter = Router();

/** Public — list bundled sample resumes (no text body) */
resumeRouter.get('/samples', (_req, res) => {
  res.json({ samples: listSampleMeta() });
});

resumeRouter.use(requireAuth);

resumeRouter.get('/latest', async (req, res) => {
  const record = await getLatestAnalysis(req.user!.id);
  if (!record) {
    res.status(404).json({ error: 'No resume analysis yet', code: 'NOT_FOUND' });
    return;
  }
  res.json(record);
});

resumeRouter.get('/:id', async (req, res) => {
  const record = await getAnalysisById(req.user!.id, req.params.id);
  if (!record) {
    res.status(404).json({ error: 'Analysis not found', code: 'NOT_FOUND' });
    return;
  }
  res.json(record);
});

resumeRouter.post('/analyze-text', async (req, res) => {
  const parsed = analyzeTextSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: parsed.error.errors[0]?.message ?? 'Invalid input',
      code: 'VALIDATION_ERROR',
    });
    return;
  }

  try {
    const analysis = analyzeResumeText(parsed.data.text, parsed.data.targetRole);
    const record = await saveResumeAnalysis({
      userId: req.user!.id,
      sourceType: 'paste',
      rawText: parsed.data.text,
      analysis,
    });
    res.status(201).json(record);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Analysis failed';
    res.status(400).json({ error: message, code: 'ANALYSIS_ERROR' });
  }
});

resumeRouter.post('/analyze-sample', async (req, res) => {
  const parsed = analyzeSampleSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: parsed.error.errors[0]?.message ?? 'Invalid input',
      code: 'VALIDATION_ERROR',
    });
    return;
  }

  const sample = getSampleById(parsed.data.sampleId);
  if (!sample) {
    res.status(404).json({ error: 'Sample not found', code: 'NOT_FOUND' });
    return;
  }

  try {
    const analysis = analyzeResumeText(sample.text, parsed.data.targetRole);
    const record = await saveResumeAnalysis({
      userId: req.user!.id,
      sourceType: 'sample',
      sampleId: sample.id,
      fileName: sample.title,
      rawText: sample.text,
      analysis,
    });
    res.status(201).json(record);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Analysis failed';
    res.status(400).json({ error: message, code: 'ANALYSIS_ERROR' });
  }
});

resumeRouter.post('/upload', upload.single('file'), async (req, res) => {
  if (!req.file) {
    res.status(400).json({ error: 'No file uploaded', code: 'NO_FILE' });
    return;
  }

  const targetRole = req.body.targetRole as string | undefined;
  const roleParsed = z
    .enum(['qa_tester', 'data_analyst', 'project_manager', 'ai_reviewer'])
    .optional()
    .safeParse(targetRole);

  try {
    const text = await extractTextFromFile(
      req.file.buffer,
      req.file.mimetype,
      req.file.originalname,
    );
    const analysis = analyzeResumeText(text, roleParsed.success ? roleParsed.data : undefined);
    const record = await saveResumeAnalysis({
      userId: req.user!.id,
      sourceType: 'upload',
      fileName: req.file.originalname,
      rawText: text,
      analysis,
    });
    res.status(201).json(record);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Upload failed';
    res.status(400).json({ error: message, code: 'UPLOAD_ERROR' });
  }
});
