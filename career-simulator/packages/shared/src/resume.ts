import type { SimRole } from '@career-sim/shared';

export type ResumeProject = {
  name: string;
  description: string;
};

export type JobMatchScore = {
  role: SimRole;
  label: string;
  score: number;
  rationale: string;
};

export type LearningRoadmapItem = {
  step: number;
  title: string;
  description: string;
  estimatedDays: number;
};

export type PracticeProject = {
  title: string;
  description: string;
  role: SimRole;
};

export type ResumeAnalysis = {
  skills: string[];
  experienceYears: number | null;
  experienceSummary: string[];
  projects: ResumeProject[];
  suggestedRoles: SimRole[];
  jobMatchScores: JobMatchScore[];
  learningRoadmap: LearningRoadmapItem[];
  practiceProjects: PracticeProject[];
  strengths: string[];
  gaps: string[];
  headline: string;
};

export type ResumeSampleMeta = {
  id: string;
  title: string;
  persona: string;
  targetRoles: string[];
};

export type ResumeAnalysisRecord = {
  id: string;
  sourceType: 'upload' | 'paste' | 'sample';
  fileName: string | null;
  sampleId: string | null;
  analysis: ResumeAnalysis;
  createdAt: string;
};

export type AnalyzeTextRequest = {
  text: string;
  targetRole?: SimRole;
};

export type AnalyzeSampleRequest = {
  sampleId: string;
  targetRole?: SimRole;
};
