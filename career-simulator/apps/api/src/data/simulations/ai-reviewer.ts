import type { SimModuleDetail } from '@career-sim/shared';

export const AI_REVIEW_SAMPLES = [
  {
    id: 'sample-a',
    prompt: 'What is the refund policy for ValleyPay premium?',
    response: `ValleyPay Premium members can request a full refund within 30 days of purchase by emailing support@valleypay.com. Refunds process in 5–7 business days.`,
    issue: 'none',
  },
  {
    id: 'sample-b',
    prompt: 'Does ValleyPay share data with the IRS automatically?',
    response: `Yes, ValleyPay automatically sends all customer transaction history to the IRS every night as required by federal law section 8899-B.`,
    issue: 'hallucination',
  },
  {
    id: 'sample-c',
    prompt: 'How do I reset my password?',
    response: `Open the app, tap Forgot password, enter your email, click the link, choose a new password with 8+ characters including a number and symbol.`,
    issue: 'none',
  },
];

export const AI_REVIEWER_SIMULATION: SimModuleDetail = {
  roleId: 'ai_reviewer',
  label: 'AI Reviewer',
  company: 'SafeReply Labs',
  projectName: 'Model Output Quality Audit',
  description: 'Rate AI answers, spot hallucinations, and write structured feedback.',
  taskCount: 4,
  tasks: [
    {
      id: 'ar-rubric',
      order: 1,
      kind: 'written',
      title: 'Define a review rubric',
      instruction:
        'Create a simple 4-criteria rubric for reviewing customer-support AI answers. Name each criterion and describe what "good" looks like in one sentence.',
      scenario: `You are designing quality standards for a fintech chatbot review team.`,
      hints: [
        'Common criteria: accuracy, completeness, tone, safety/compliance.',
        'Make criteria observable — a reviewer can say yes/no.',
      ],
      passScore: 65,
    },
    {
      id: 'ar-rate',
      order: 2,
      kind: 'review',
      title: 'Rate sample AI answers',
      instruction:
        'Review the three sample Q&A pairs. Rate accuracy (1–5) for each and flag any hallucination or unsafe claim.',
      scenario: `Samples are shown in the task form — read each response carefully against the user question.`,
      hints: [
        'Hallucination = confident false fact not supported by policy.',
        'Sample B contains a fabricated legal requirement.',
      ],
      passScore: 75,
    },
    {
      id: 'ar-feedback',
      order: 3,
      kind: 'written',
      title: 'Write improvement feedback',
      instruction:
        'Pick the worst sample response and write structured feedback for the model team: what went wrong, user impact, and a suggested fix.',
      scenario: `Your feedback will go into an internal quality ticket.`,
      hints: [
        'Be specific — quote the problematic sentence.',
        'Suggest safer wording or "I don\'t know" escalation.',
      ],
      passScore: 70,
    },
    {
      id: 'ar-policy',
      order: 4,
      kind: 'written',
      title: 'Draft a reviewer checklist',
      instruction:
        'Write a 5-item checklist another reviewer could use before approving an AI answer for production.',
      scenario: `Checklist must be usable by a new hire on day one.`,
      hints: [
        'Include fact-check, tone, PII, escalation triggers.',
        'One line per item — action-oriented.',
      ],
      passScore: 65,
    },
  ],
};
