import type { ResumeSampleMeta } from '@career-sim/shared';
import {
  SAMPLE_FRESHER_DA,
  SAMPLE_PM_COORDINATOR,
  SAMPLE_QA_RETURNER,
} from './content';

export type ResumeSample = ResumeSampleMeta & { text: string };

export const RESUME_SAMPLES: ResumeSample[] = [
  {
    id: 'qa-returner',
    title: 'QA career returner',
    persona: '3 years QA experience, career gap, restarting in tech',
    targetRoles: ['QA Tester', 'Project Coordinator'],
    text: SAMPLE_QA_RETURNER,
  },
  {
    id: 'fresher-analyst',
    title: 'Fresh graduate — Data Analyst',
    persona: 'Recent stats grad, internships, portfolio projects',
    targetRoles: ['Data Analyst'],
    text: SAMPLE_FRESHER_DA,
  },
  {
    id: 'pm-coordinator',
    title: 'Project Coordinator → PM',
    persona: 'Insurance ops, sprint facilitation, risk tracking',
    targetRoles: ['Project Manager', 'QA Tester'],
    text: SAMPLE_PM_COORDINATOR,
  },
];

export function getSampleById(id: string): ResumeSample | undefined {
  return RESUME_SAMPLES.find((s) => s.id === id);
}

export function listSampleMeta(): ResumeSampleMeta[] {
  return RESUME_SAMPLES.map(({ id, title, persona, targetRoles }) => ({
    id,
    title,
    persona,
    targetRoles,
  }));
}
