export type SimRole =
  | 'qa_tester'
  | 'data_analyst'
  | 'project_manager'
  | 'ai_reviewer';

export const SIM_ROLES: { id: SimRole; label: string; description: string }[] = [
  {
    id: 'qa_tester',
    label: 'QA Tester',
    description: 'Test cases, bug reports, defect priority, mock login testing',
  },
  {
    id: 'data_analyst',
    label: 'Data Analyst',
    description: 'Dataset analysis, charts, insights, summary reports',
  },
  {
    id: 'project_manager',
    label: 'Project Manager',
    description: 'Plans, milestones, risk analysis, sprint planning',
  },
  {
    id: 'ai_reviewer',
    label: 'AI Reviewer',
    description: 'Evaluate AI outputs, detect hallucinations, feedback reports',
  },
];
