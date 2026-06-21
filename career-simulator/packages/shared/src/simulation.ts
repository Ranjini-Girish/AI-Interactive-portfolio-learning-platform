import type { SimRole } from './roles';

export type SimTaskKind =
  | 'written'
  | 'test_cases'
  | 'bug_report'
  | 'prioritize'
  | 'review';

export type SimTaskDefinition = {
  id: string;
  order: number;
  kind: SimTaskKind;
  title: string;
  instruction: string;
  scenario: string;
  hints: string[];
  passScore: number;
};

export type SimModuleMeta = {
  roleId: SimRole;
  label: string;
  company: string;
  projectName: string;
  description: string;
  taskCount: number;
};

export type SimModuleDetail = SimModuleMeta & {
  tasks: SimTaskDefinition[];
};

export type SimTaskStatus = 'locked' | 'available' | 'submitted' | 'passed' | 'needs_revision';

export type SimTaskProgress = {
  taskId: string;
  status: SimTaskStatus;
  score: number | null;
  feedback: string[];
  submittedAt: string | null;
};

export type SimulationSessionRecord = {
  id: string;
  roleId: SimRole;
  status: 'in_progress' | 'completed';
  progressPercent: number;
  tasksCompleted: number;
  totalTasks: number;
  startedAt: string;
  completedAt: string | null;
  tasks: SimTaskProgress[];
};

export type SimModuleOverview = SimModuleMeta & {
  session: SimulationSessionRecord | null;
};

export type SimTaskSubmitPayload =
  | { kind: 'written'; text: string }
  | { kind: 'test_cases'; text: string }
  | { kind: 'bug_report'; title: string; severity: string; steps: string; expected: string; actual: string }
  | { kind: 'prioritize'; order: string[] }
  | { kind: 'review'; ratings: Record<string, number>; feedback: string };

export type SimTaskSubmitResult = {
  score: number;
  passed: boolean;
  feedback: string[];
  status: 'passed' | 'needs_revision';
};
