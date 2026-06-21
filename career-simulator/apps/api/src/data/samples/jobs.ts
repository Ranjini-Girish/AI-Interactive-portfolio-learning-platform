import type { JobSampleMeta } from '@career-sim/shared';
import { JD_DATA_ANALYST, JD_PM_INSURANCE, JD_QA_FINTECH } from './jd-content';

export type JobSample = JobSampleMeta & { text: string };

export const JOB_SAMPLES: JobSample[] = [
  {
    id: 'qa-fintech',
    title: 'QA Tester — Mobile Banking',
    company: 'Willamette Valley Digital',
    role: 'QA Tester',
    text: JD_QA_FINTECH,
  },
  {
    id: 'data-analyst-remote',
    title: 'Data Analyst I (Remote)',
    company: 'Northwest Health Analytics',
    role: 'Data Analyst',
    text: JD_DATA_ANALYST,
  },
  {
    id: 'pm-insurance',
    title: 'Project Coordinator / Junior PM',
    company: 'Midwest Insurance Group',
    role: 'Project Manager',
    text: JD_PM_INSURANCE,
  },
];

export function listJobSampleMeta(): JobSampleMeta[] {
  return JOB_SAMPLES.map(({ id, title, company, role }) => ({ id, title, company, role }));
}

export function getJobSampleById(id: string): JobSample | undefined {
  return JOB_SAMPLES.find((s) => s.id === id);
}
