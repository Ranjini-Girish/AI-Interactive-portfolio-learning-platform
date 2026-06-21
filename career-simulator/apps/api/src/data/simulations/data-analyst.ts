import type { SimModuleDetail } from '@career-sim/shared';

export const DATA_ANALYST_DATASET = [
  { month: 'Jan', region: 'West', product: 'Wellness Kit', revenue: 42000, units: 840 },
  { month: 'Jan', region: 'East', product: 'Wellness Kit', revenue: 31000, units: 620 },
  { month: 'Feb', region: 'West', product: 'Wellness Kit', revenue: 45000, units: 900 },
  { month: 'Feb', region: 'East', product: 'Wellness Kit', revenue: 28000, units: 560 },
  { month: 'Mar', region: 'West', product: 'Care Plus', revenue: 52000, units: 650 },
  { month: 'Mar', region: 'East', product: 'Care Plus', revenue: 48000, units: 600 },
  { month: 'Mar', region: 'West', product: 'Wellness Kit', revenue: 39000, units: 780 },
];

export const DATA_ANALYST_SIMULATION: SimModuleDetail = {
  roleId: 'data_analyst',
  label: 'Data Analyst',
  company: 'Northwest Health Analytics',
  projectName: 'Q1 Retail Sales Review',
  description: 'Explore a sample dataset, find insights, and write a stakeholder summary.',
  taskCount: 4,
  tasks: [
    {
      id: 'da-explore',
      order: 1,
      kind: 'written',
      title: 'Explore the dataset',
      instruction:
        'Review the Q1 sales sample data (shown on this page). Write 3 bullet insights supported by numbers from the data.',
      scenario: `Dataset: Northwest Health Analytics — Q1 product sales by region (sample rows provided in the task UI).

Business question: Which region and product should marketing invest in for Q2?`,
      hints: [
        'Compare West vs East totals or growth.',
        'Mention specific dollar amounts or unit counts.',
        'Care Plus launched strong in March — call that out if you see it.',
      ],
      passScore: 70,
    },
    {
      id: 'da-chart-narrative',
      order: 2,
      kind: 'written',
      title: 'Chart narrative',
      instruction:
        'Imagine you built a bar chart of revenue by product. Write 2–3 sentences explaining what the chart shows and why it matters to leadership.',
      scenario: `Audience: VP of Sales — 60-second read before a meeting.`,
      hints: ['Lead with the headline finding.', 'Connect the number to a business action.'],
      passScore: 65,
    },
    {
      id: 'da-sql-thought',
      order: 3,
      kind: 'written',
      title: 'SQL thinking exercise',
      instruction:
        'In plain English (no need for perfect SQL syntax), describe how you would query total revenue by region for March. List the columns you would use and any filters.',
      scenario: `Table name: sales_fact with columns month, region, product, revenue, units`,
      hints: [
        'Filter month = March.',
        'Group by region and sum revenue.',
      ],
      passScore: 60,
    },
    {
      id: 'da-summary',
      order: 4,
      kind: 'written',
      title: 'One-page stakeholder summary',
      instruction:
        'Write a short email-style summary (5–8 sentences) for stakeholders: key findings, one risk, and a recommended next step.',
      scenario: `Subject: Q1 Sales Review — preliminary findings`,
      hints: [
        'Structure: Findings → Risk/uncertainty → Recommendation.',
        'Keep jargon out — write for a busy executive.',
      ],
      passScore: 70,
    },
  ],
};
