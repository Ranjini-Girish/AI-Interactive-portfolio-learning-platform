/** Plain-language labels for non-IT visitors */

export const DOMAIN_LABELS: Record<string, string> = {
  banking: 'Banking & finance',
  retail: 'Shopping & retail',
  insurance: 'Insurance',
  genai: 'AI & smart assistants',
};

export const HOW_IT_WORKS = [
  {
    step: 1,
    title: 'Open a real project demo',
    body: 'Start with Customer Grouping Lab — banking-style segmentation you can show on a screen share.',
    icon: '🎯',
  },
  {
    step: 2,
    title: 'Run it with practice data',
    body: 'One click loads sample data. No coding for Project 1 — create groups and read the chart.',
    icon: '▶️',
  },
  {
    step: 3,
    title: 'Save your proof story',
    body: 'Mark steps in the learning path and practice a 60-second “what I built” answer for interviews.',
    icon: '✓',
  },
] as const;

export const GLOSSARY: { term: string; plain: string }[] = [
  {
    term: 'Build Lab',
    plain: 'Your step-by-step learning path with checklists and an AI helper — like a guided tutorial.',
  },
  {
    term: 'Portfolio',
    plain: 'A gallery of working apps you can open and try, tied to real resume projects.',
  },
  {
    term: 'Milestone',
    plain: 'One chapter in a project — broken into small steps so you never feel lost.',
  },
  {
    term: 'Demo',
    plain: 'The actual app running in your browser — click buttons and see results.',
  },
  {
    term: 'Customer segmentation',
    plain: 'Sorting customers into groups who behave similarly (e.g. big spenders vs savers).',
  },
];

export const RECOMMENDED_FIRST = {
  slug: 'customer-segmentation-lab',
  title: 'Customer Grouping Lab',
  why: 'Fastest proof point — recruiters can see you grouped bank customers with real ML workflow, in one sitting.',
  demoPath: '/demos/customer-segmentation-lab',
  learnPath: '/build/projects/customer-segmentation-lab',
} as const;

export const STATUS_LABELS: Record<string, string> = {
  live: 'Ready to try',
  scaffolded: 'Ready to try',
  planned: 'Coming soon',
};
