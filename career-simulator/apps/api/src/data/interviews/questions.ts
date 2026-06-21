import type { InterviewQuestion, SimRole } from '@career-sim/shared';

const BEHAVIORAL: InterviewQuestion[] = [
  {
    id: 'beh-team-conflict',
    type: 'behavioral',
    text: 'Tell me about a time you disagreed with a teammate. How did you handle it?',
    tip: 'Use STAR: Situation, Task, Action, Result. Stay professional — focus on collaboration.',
  },
  {
    id: 'beh-tight-deadline',
    type: 'behavioral',
    text: 'Describe a situation where you had a tight deadline. What did you prioritize?',
    tip: 'Show how you communicated risk early and delivered what mattered most.',
  },
  {
    id: 'beh-learn-quickly',
    type: 'behavioral',
    text: 'Tell me about learning something new quickly for a project or role.',
    tip: 'Mention concrete steps: docs, mentor, practice, feedback loop.',
  },
  {
    id: 'beh-mistake',
    type: 'behavioral',
    text: 'Tell me about a mistake you made at work. What did you learn?',
    tip: 'Own the mistake, explain the fix, and what you do differently now.',
  },
];

const TECHNICAL_QA: InterviewQuestion[] = [
  {
    id: 'tech-qa-test-case',
    type: 'technical',
    text: 'How would you test a login page? What test cases would you write first?',
    tip: 'Cover happy path, invalid credentials, empty fields, and security basics.',
  },
  {
    id: 'tech-qa-bug-report',
    type: 'technical',
    text: 'What belongs in a good bug report? Walk me through your template.',
    tip: 'Title, severity, steps, expected vs actual, environment.',
  },
  {
    id: 'tech-qa-regression',
    type: 'technical',
    text: 'Explain the difference between smoke testing and regression testing.',
    tip: 'Smoke = quick health check; regression = ensure old features still work.',
  },
  {
    id: 'tech-qa-api',
    type: 'technical',
    text: 'How would you test an API endpoint using Postman or a similar tool?',
    tip: 'Method, URL, headers, body, status code, response body validation.',
  },
];

const TECHNICAL_DA: InterviewQuestion[] = [
  {
    id: 'tech-da-sql',
    type: 'technical',
    text: 'How would you find total revenue by region from a sales table?',
    tip: 'Filter, GROUP BY region, SUM(revenue). Mention data quality checks.',
  },
  {
    id: 'tech-da-insight',
    type: 'technical',
    text: 'You see a sudden drop in weekly signups. What is your analysis approach?',
    tip: 'Confirm the data, segment by channel/region, check for external events.',
  },
  {
    id: 'tech-da-viz',
    type: 'technical',
    text: 'When would you use a bar chart vs a line chart?',
    tip: 'Bar = compare categories; line = trends over time.',
  },
  {
    id: 'tech-da-stakeholder',
    type: 'technical',
    text: 'How do you explain a technical finding to a non-technical stakeholder?',
    tip: 'Lead with the business impact, one chart, plain language, next step.',
  },
];

const TECHNICAL_PM: InterviewQuestion[] = [
  {
    id: 'tech-pm-risk',
    type: 'technical',
    text: 'How do you identify and track project risks?',
    tip: 'Risk register: impact, likelihood, owner, mitigation, review cadence.',
  },
  {
    id: 'tech-pm-sprint',
    type: 'technical',
    text: 'What makes a good sprint goal?',
    tip: 'One clear outcome, achievable in the sprint, measurable, team-aligned.',
  },
  {
    id: 'tech-pm-scope',
    type: 'technical',
    text: 'A stakeholder asks for scope creep mid-sprint. What do you do?',
    tip: 'Acknowledge request, assess impact, trade-offs, document decision.',
  },
  {
    id: 'tech-pm-status',
    type: 'technical',
    text: 'How do you write an effective weekly status update?',
    tip: 'RAG status, progress, blockers, decisions needed, next week focus.',
  },
];

const TECHNICAL_AR: InterviewQuestion[] = [
  {
    id: 'tech-ar-hallucination',
    type: 'technical',
    text: 'How do you detect hallucinations in an AI-generated answer?',
    tip: 'Fact-check claims, compare to policy, flag unsupported specifics.',
  },
  {
    id: 'tech-ar-rubric',
    type: 'technical',
    text: 'What criteria would you use to rate a customer-support AI response?',
    tip: 'Accuracy, completeness, tone, safety, escalation when unsure.',
  },
  {
    id: 'tech-ar-feedback',
    type: 'technical',
    text: 'How would you write feedback for a model team after a bad answer?',
    tip: 'Quote the issue, user impact, severity, suggested fix or guardrail.',
  },
  {
    id: 'tech-ar-edge',
    type: 'technical',
    text: 'When should an AI assistant refuse to answer or escalate to a human?',
    tip: 'Legal/medical/financial advice, PII, low confidence, policy violations.',
  },
];

const TECH_BY_ROLE: Record<SimRole, InterviewQuestion[]> = {
  qa_tester: TECHNICAL_QA,
  data_analyst: TECHNICAL_DA,
  project_manager: TECHNICAL_PM,
  ai_reviewer: TECHNICAL_AR,
};

export function pickInterviewQuestions(
  roleId: SimRole,
  mode: 'behavioral' | 'technical' | 'mixed',
): InterviewQuestion[] {
  const technical = TECH_BY_ROLE[roleId] ?? TECHNICAL_QA;

  if (mode === 'behavioral') return BEHAVIORAL.slice(0, 4);
  if (mode === 'technical') return technical.slice(0, 4);

  return [...BEHAVIORAL.slice(0, 3), ...technical.slice(0, 3)];
}

export function getQuestionById(questionId: string, roleId: SimRole): InterviewQuestion | null {
  const all = [...BEHAVIORAL, ...(TECH_BY_ROLE[roleId] ?? TECHNICAL_QA)];
  return all.find((q) => q.id === questionId) ?? null;
}

export function listQuestionPreview(roleId: SimRole) {
  return {
    behavioral: BEHAVIORAL.length,
    technical: (TECH_BY_ROLE[roleId] ?? TECHNICAL_QA).length,
  };
}
