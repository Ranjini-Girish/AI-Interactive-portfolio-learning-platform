import { Router } from 'express';
import { healthRouter } from './health';
import { authRouter } from './auth';
import { resumeRouter } from './resume';
import { jobRouter } from './job';
import { mentorRouter } from './mentor';
import { simulationRouter } from './simulation';
import { progressRouter } from './progress';
import { portfolioRouter } from './portfolio';
import { interviewRouter } from './interview';

export const apiRouter = Router();

apiRouter.use(healthRouter);
apiRouter.use('/auth', authRouter);
apiRouter.use('/resume', resumeRouter);
apiRouter.use('/job', jobRouter);
apiRouter.use('/mentor', mentorRouter);
apiRouter.use('/simulation', simulationRouter);
apiRouter.use('/progress', progressRouter);
apiRouter.use('/portfolio', portfolioRouter);
apiRouter.use('/interview', interviewRouter);
