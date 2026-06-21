import { Router } from 'express';
import { requireAuth } from '../middleware/auth';
import { getLatestAnalysis } from '../repositories/resume-repository';
import { getLatestPortfolio, hasPortfolio, savePortfolio } from '../repositories/portfolio-repository';
import {
  generatePortfolio,
  isPortfolioAiConfigured,
} from '../services/portfolio-generator';
import { getMentorModel } from '../services/mentor-prompt';

export const portfolioRouter = Router();

portfolioRouter.use(requireAuth);

portfolioRouter.get('/status', async (req, res) => {
  const resume = await getLatestAnalysis(req.user!.id);
  const hasGen = await hasPortfolio(req.user!.id);
  res.json({
    configured: isPortfolioAiConfigured(),
    model: getMentorModel(),
    hasResume: Boolean(resume),
    hasGeneration: hasGen,
  });
});

portfolioRouter.get('/latest', async (req, res) => {
  const record = await getLatestPortfolio(req.user!.id);
  if (!record) {
    res.status(404).json({ error: 'No portfolio yet — generate one first', code: 'NOT_FOUND' });
    return;
  }
  res.json(record);
});

portfolioRouter.post('/generate', async (req, res) => {
  try {
    const content = await generatePortfolio(req.user!.id, req.user!.fullName);
    const record = await savePortfolio(req.user!.id, content);
    res.status(201).json(record);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Generation failed';
    const code = message.includes('resume') ? 'NO_RESUME' : 'GENERATION_ERROR';
    res.status(message.includes('DATABASE') ? 503 : 400).json({ error: message, code });
  }
});
