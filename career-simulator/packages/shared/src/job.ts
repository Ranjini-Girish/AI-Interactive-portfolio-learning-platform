import type { SimRole } from './roles';

export type JobSampleMeta = {
  id: string;
  title: string;
  company: string;
  role: string;
};

export type AnalyzeJobRequest = {
  jdText: string;
  targetRole?: SimRole;
  resumeAnalysisId?: string;
};

export type AnalyzeJobSampleRequest = {
  sampleId: string;
  targetRole?: SimRole;
  resumeAnalysisId?: string;
};

export type JobMatchRecord = {
  id: string;
  sourceType: 'paste' | 'sample';
  sampleId: string | null;
  resumeAnalysisId: string | null;
  jobTitle: string;
  analysis: JobMatchAnalysis;
  createdAt: string;
};

export type JobMatchAnalysis = {
  jobTitle: string;
  inferredRole: SimRole;
  requiredSkills: string[];
  preferredSkills: string[];
  toolsMentioned: string[];
  resumeSkills: string[];
  matchedSkills: string[];
  skillGaps: string[];
  missingTools: string[];
  overallMatchScore: number;
  learningPath: {
    step: number;
    title: string;
    description: string;
    estimatedDays: number;
  }[];
  plainSummary: string;
};
