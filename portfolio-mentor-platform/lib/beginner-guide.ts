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
    title: 'Pick a real-world topic',
    body: 'Choose banking, shopping, insurance, or AI — each project mirrors real job experience.',
    icon: '🎯',
  },
  {
    step: 2,
    title: 'Try the live demo',
    body: 'Click “Try it now.” No coding needed for Project 1 — use practice data and follow on-screen steps.',
    icon: '▶️',
  },
  {
    step: 3,
    title: 'Track your progress',
    body: 'Open the learning path, check off what you tried, and mark steps complete when you’re done.',
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
  why: 'Best for beginners — no spreadsheet prep, no coding. One click loads practice bank data.',
  demoPath: '/demos/customer-segmentation-lab',
  learnPath: '/build/projects/customer-segmentation-lab',
} as const;

export const STATUS_LABELS: Record<string, string> = {
  live: 'Ready to try',
  scaffolded: 'Ready to try',
  planned: 'Coming soon',
};
