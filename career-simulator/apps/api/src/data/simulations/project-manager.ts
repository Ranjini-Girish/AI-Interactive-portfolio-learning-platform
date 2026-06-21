import type { SimModuleDetail } from '@career-sim/shared';

export const PM_SIMULATION: SimModuleDetail = {
  roleId: 'project_manager',
  label: 'Project Manager',
  company: 'Cascade Product Studio',
  projectName: 'Customer Portal Redesign',
  description: 'Draft plans, assess risks, and plan a sprint like a real PM.',
  taskCount: 4,
  tasks: [
    {
      id: 'pm-plan',
      order: 1,
      kind: 'written',
      title: 'Draft a project plan',
      instruction:
        'Write a lightweight project plan with at least 3 milestones, target dates or weeks, and who owns each milestone (role names are fine).',
      scenario: `Project: Redesign the customer self-service portal for a mid-size utility company.
Timeline: 10 weeks. Team: 2 engineers, 1 designer, 1 QA, you as PM.
Constraints: Must launch before peak billing season (week 10).`,
      hints: [
        'Typical phases: discovery → design → build → test → launch.',
        'Name milestones clearly (e.g. "Design sign-off — Week 3").',
      ],
      passScore: 70,
    },
    {
      id: 'pm-risks',
      order: 2,
      kind: 'written',
      title: 'Risk analysis',
      instruction:
        'List at least 3 project risks. For each, include impact, likelihood (low/medium/high), and a mitigation action.',
      scenario: `Same portal redesign — stakeholders are worried about scope creep and vendor API delays.`,
      hints: [
        'Risks can be technical, resource, or schedule-related.',
        'Mitigation = what you would do before the risk hurts the project.',
      ],
      passScore: 70,
    },
    {
      id: 'pm-sprint',
      order: 3,
      kind: 'written',
      title: 'Plan a two-week sprint',
      instruction:
        'Write a sprint goal and 4–6 user stories (or tasks) for the first development sprint. Each story should be one line with a clear outcome.',
      scenario: `Sprint 1 focus: Authentication + account dashboard shell (no billing yet).`,
      hints: [
        'Start stories with "As a customer I can…" or verb phrases like "Implement login page".',
        'Include at least one QA/testing story.',
      ],
      passScore: 65,
    },
    {
      id: 'pm-status',
      order: 4,
      kind: 'written',
      title: 'Executive status update',
      instruction:
        'Write a brief status email to an executive: overall RAG status (green/amber/red), progress, blockers, and ask (if any).',
      scenario: `Week 4 of 10 — design finished, development 40% done, one engineer out sick this week.`,
      hints: [
        'Executives want: status color, headline, blocker, decision needed.',
        'Keep under 150 words.',
      ],
      passScore: 65,
    },
  ],
};
