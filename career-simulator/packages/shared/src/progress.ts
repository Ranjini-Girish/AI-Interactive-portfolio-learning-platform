import type { SimRole } from './roles';

export type ProgressWeakArea = {
  id: string;
  label: string;
  source: 'resume' | 'job_match' | 'simulation' | 'tools';
  detail?: string;
};

export type ProgressNextStep = {
  id: string;
  title: string;
  description: string;
  href: string;
  priority: 'high' | 'medium' | 'low';
};

export type ProgressModuleSummary = {
  roleId: SimRole;
  label: string;
  status: 'not_started' | 'in_progress' | 'completed';
  progressPercent: number;
  tasksCompleted: number;
  totalTasks: number;
};

export type ProgressLearningStep = {
  step: number;
  title: string;
  description: string;
  estimatedDays: number;
  status: 'done' | 'current' | 'upcoming';
};

export type ProgressDashboard = {
  phase: number;
  message: string;
  readiness: {
    score: number;
    label: 'Getting started' | 'Building skills' | 'Interview ready' | 'Job ready';
    breakdown: {
      resumeMatch: number | null;
      jobMatch: number | null;
      simulationProgress: number;
    };
  };
  stats: {
    skillsIdentified: number;
    skillsPracticed: number;
    tasksCompleted: number;
    totalSimulationTasks: number;
    modulesCompleted: number;
    totalModules: number;
    projectCompletionPercent: number;
    modulesInProgress: number;
  };
  skillsLearned: string[];
  weakAreas: ProgressWeakArea[];
  nextSteps: ProgressNextStep[];
  modules: ProgressModuleSummary[];
  learningPath: ProgressLearningStep[];
  resume: {
    id: string;
    headline: string;
    topRole: string | null;
    topScore: number | null;
  } | null;
  jobMatch: {
    id: string;
    jobTitle: string;
    matchScore: number;
    gapCount: number;
  } | null;
  activeSimulation: {
    roleId: SimRole;
    label: string;
    progressPercent: number;
    tasksCompleted: number;
    totalTasks: number;
  } | null;
};
