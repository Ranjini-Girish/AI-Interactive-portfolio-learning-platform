import type { ResumeAnalysis, SimRole } from '@career-sim/shared';
import { SIM_ROLES } from '@career-sim/shared';

const SKILL_PATTERNS: { skill: string; patterns: RegExp[] }[] = [
  { skill: 'Manual Testing', patterns: [/manual test/i, /manual testing/i] },
  { skill: 'Test Cases', patterns: [/test case/i, /test scripts/i] },
  { skill: 'Bug Reporting', patterns: [/bug report/i, /defect/i, /logged defects/i] },
  { skill: 'Jira', patterns: [/\bjira\b/i] },
  { skill: 'Postman', patterns: [/\bpostman\b/i] },
  { skill: 'Regression Testing', patterns: [/regression/i] },
  { skill: 'Agile/Scrum', patterns: [/\bagile\b/i, /\bscrum\b/i, /standup/i, /sprint/i] },
  { skill: 'SQL', patterns: [/\bsql\b/i, /postgresql/i, /mysql/i] },
  { skill: 'Python', patterns: [/\bpython\b/i, /\bpandas\b/i] },
  { skill: 'Excel', patterns: [/\bexcel\b/i] },
  { skill: 'Tableau', patterns: [/\btableau\b/i] },
  { skill: 'Data Cleaning', patterns: [/data clean/i, /missing values/i, /duplicates/i] },
  { skill: 'Visualization', patterns: [/chart/i, /dashboard/i, /visual/i] },
  { skill: 'Statistics', patterns: [/statistic/i, /regression model/i] },
  { skill: 'Project Planning', patterns: [/project plan/i, /timeline/i, /milestone/i] },
  { skill: 'Risk Management', patterns: [/risk/i] },
  { skill: 'Stakeholder Communication', patterns: [/stakeholder/i, /status report/i, /leadership/i] },
  { skill: 'Microsoft Project', patterns: [/microsoft project/i, /smartsheet/i] },
  { skill: 'UAT Coordination', patterns: [/\buat\b/i] },
  { skill: 'Git', patterns: [/\bgit\b/i, /github/i] },
  { skill: 'API Testing', patterns: [/api test/i, /api smoke/i, /postman/i] },
  { skill: 'Attention to Detail', patterns: [/attention to detail/i] },
  { skill: 'AI Evaluation', patterns: [/\bai\b/i, /hallucin/i, /llm/i, /prompt/i] },
];

const ROLE_SKILL_WEIGHTS: Record<SimRole, { required: string[]; nice: string[] }> = {
  qa_tester: {
    required: ['Manual Testing', 'Test Cases', 'Bug Reporting', 'Jira'],
    nice: ['Regression Testing', 'Agile/Scrum', 'Postman', 'SQL', 'API Testing'],
  },
  data_analyst: {
    required: ['Python', 'SQL', 'Excel', 'Visualization'],
    nice: ['Tableau', 'Data Cleaning', 'Statistics', 'Git'],
  },
  project_manager: {
    required: ['Project Planning', 'Agile/Scrum', 'Stakeholder Communication', 'Risk Management'],
    nice: ['Jira', 'Microsoft Project', 'UAT Coordination'],
  },
  ai_reviewer: {
    required: ['AI Evaluation', 'Attention to Detail'],
    nice: ['Bug Reporting', 'Agile/Scrum', 'Python'],
  },
};

const PRACTICE_BY_ROLE: Record<SimRole, { title: string; description: string }[]> = {
  qa_tester: [
    {
      title: 'Mock login test plan',
      description: 'Write 10 test cases for a sample banking login page including edge cases.',
    },
    {
      title: 'Defect report workshop',
      description: 'File 3 sample bugs with severity, steps, and expected vs actual results.',
    },
  ],
  data_analyst: [
    {
      title: 'Retail CSV insight sprint',
      description: 'Clean a sample dataset, chart top categories, write a 1-page stakeholder summary.',
    },
    {
      title: 'KPI dashboard story',
      description: 'Pick 3 metrics and explain trends in plain language for a non-technical manager.',
    },
  ],
  project_manager: [
    {
      title: 'Two-week sprint plan',
      description: 'Break a sample feature into backlog items, owners, and acceptance criteria.',
    },
    {
      title: 'Risk register exercise',
      description: 'Identify 5 project risks with likelihood, impact, and mitigation steps.',
    },
  ],
  ai_reviewer: [
    {
      title: 'Hallucination hunt',
      description: 'Review 5 AI answers, flag unsupported claims, and rewrite safe responses.',
    },
    {
      title: 'Rubric design lab',
      description: 'Create a 5-criteria scoring rubric for evaluating customer-support AI replies.',
    },
  ],
};

const ROADMAP_BY_ROLE: Record<SimRole, ResumeAnalysis['learningRoadmap']> = {
  qa_tester: [
    {
      step: 1,
      title: 'Testing fundamentals refresher',
      description:
        'Relearn test case structure, equivalence partitioning, and boundary values with everyday examples.',
      estimatedDays: 3,
    },
    {
      step: 2,
      title: 'Tool practice: Jira + Postman',
      description: 'Log 5 practice defects and run 3 API smoke tests on a sample endpoint.',
      estimatedDays: 4,
    },
    {
      step: 3,
      title: 'Agile team simulation',
      description: 'Join the QA work simulation module and complete a mock sprint release.',
      estimatedDays: 5,
    },
  ],
  data_analyst: [
    {
      step: 1,
      title: 'SQL & Excel warm-up',
      description: 'Filter, group, and chart a sample sales dataset; explain one insight aloud.',
      estimatedDays: 4,
    },
    {
      step: 2,
      title: 'Python pandas mini-project',
      description: 'Clean missing values and compute top-5 categories from CSV.',
      estimatedDays: 5,
    },
    {
      step: 3,
      title: 'Stakeholder summary writing',
      description: 'Turn charts into a one-page narrative a manager can act on.',
      estimatedDays: 3,
    },
  ],
  project_manager: [
    {
      step: 1,
      title: 'Plan a sample release',
      description: 'Draft milestones, owners, and a simple RACI for a 6-week feature.',
      estimatedDays: 4,
    },
    {
      step: 2,
      title: 'Risk & communication drills',
      description: 'Maintain a risk log and write a weekly status email.',
      estimatedDays: 3,
    },
    {
      step: 3,
      title: 'Sprint simulation',
      description: 'Facilitate a mock planning session with backlog prioritization.',
      estimatedDays: 5,
    },
  ],
  ai_reviewer: [
    {
      step: 1,
      title: 'Evaluate AI outputs safely',
      description: 'Learn to spot hallucinations, bias, and unsupported claims.',
      estimatedDays: 3,
    },
    {
      step: 2,
      title: 'Build a review rubric',
      description: 'Score sample answers on accuracy, tone, and completeness.',
      estimatedDays: 4,
    },
    {
      step: 3,
      title: 'Feedback report practice',
      description: 'Write actionable reviewer notes engineers can implement.',
      estimatedDays: 3,
    },
  ],
};

function extractSkills(text: string): string[] {
  const found = new Set<string>();
  for (const { skill, patterns } of SKILL_PATTERNS) {
    if (patterns.some((p) => p.test(text))) found.add(skill);
  }

  const skillsSection = text.match(/SKILLS[\s\S]*?(?=PROJECTS|EDUCATION|EXPERIENCE|$)/i);
  if (skillsSection) {
    skillsSection[0]
      .split(/[,•|\n]/)
      .map((s) => s.replace(/^skills\s*/i, '').trim())
      .filter((s) => s.length > 2 && s.length < 40)
      .forEach((raw) => {
        const normalized = raw.replace(/[^a-zA-Z0-9/+ ]/g, '').trim();
        if (normalized.length > 2) found.add(normalized);
      });
  }

  return [...found].slice(0, 24);
}

function extractExperienceYears(text: string): number | null {
  const explicit = text.match(/(\d+)\+?\s*years?\s*(?:of\s*)?(?:experience|in)/i);
  if (explicit) return parseInt(explicit[1], 10);

  const ranges = [...text.matchAll(/(\d{4})\s*[–—-]\s*(\d{4}|Present|present)/g)];
  if (ranges.length === 0) return null;

  let totalMonths = 0;
  const currentYear = new Date().getFullYear();
  for (const m of ranges) {
    const start = parseInt(m[1], 10);
    const end = m[2].match(/present/i) ? currentYear : parseInt(m[2], 10);
    if (!Number.isNaN(start) && !Number.isNaN(end) && end >= start) {
      totalMonths += (end - start) * 12;
    }
  }
  return totalMonths > 0 ? Math.max(1, Math.round(totalMonths / 12)) : null;
}

function extractExperienceBullets(text: string): string[] {
  const exp = text.match(/EXPERIENCE[\s\S]*?(?=SKILLS|PROJECTS|EDUCATION|$)/i);
  if (!exp) return [];

  return exp[0]
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.startsWith('•') || l.startsWith('-'))
    .map((l) => l.replace(/^[•-]\s*/, ''))
    .slice(0, 6);
}

function extractProjects(text: string): { name: string; description: string }[] {
  const block = text.match(/PROJECTS[\s\S]*?(?=EDUCATION|$)/i);
  if (!block) return [];

  const lines = block[0].split('\n').map((l) => l.trim()).filter(Boolean);
  const projects: { name: string; description: string }[] = [];

  for (const line of lines) {
    if (/^projects$/i.test(line)) continue;
    const dash = line.match(/^[•-]?\s*(.+?)\s*[—–-]\s*(.+)$/);
    if (dash) {
      projects.push({ name: dash[1].trim(), description: dash[2].trim() });
    } else if (line.startsWith('•') || line.startsWith('-')) {
      projects.push({ name: 'Project', description: line.replace(/^[•-]\s*/, '') });
    }
  }
  return projects.slice(0, 5);
}

function hasSkill(skillSet: Set<string>, name: string): boolean {
  const lower = name.toLowerCase();
  return [...skillSet].some((s) => s.includes(lower) || lower.includes(s));
}

function scoreRole(
  role: SimRole,
  skills: string[],
  experienceYears: number | null,
): { score: number; rationale: string } {
  const weights = ROLE_SKILL_WEIGHTS[role];
  const skillSet = new Set(skills.map((s) => s.toLowerCase()));

  const reqHits = weights.required.filter((r) => hasSkill(skillSet, r)).length;
  const niceHits = weights.nice.filter((r) => hasSkill(skillSet, r)).length;

  let score = Math.round(
    (reqHits / weights.required.length) * 70 +
      (niceHits / Math.max(weights.nice.length, 1)) * 20,
  );

  if (experienceYears !== null) {
    if (experienceYears >= 2) score += 10;
    else if (experienceYears >= 1) score += 5;
  }

  score = Math.min(98, Math.max(12, score));

  const missing = weights.required.filter((r) => !hasSkill(skillSet, r));
  const rationale =
    missing.length === 0
      ? `Strong overlap on core ${SIM_ROLES.find((r) => r.id === role)?.label} skills.`
      : `Good foundation; add ${missing.slice(0, 2).join(', ')} to strengthen fit.`;

  return { score, rationale };
}

function buildRoadmap(topRole: SimRole, gaps: string[]): ResumeAnalysis['learningRoadmap'] {
  const items = [...ROADMAP_BY_ROLE[topRole]];
  if (gaps.length > 0) {
    items.push({
      step: items.length + 1,
      title: `Close gap: ${gaps[0]}`,
      description: `Focused practice on ${gaps[0]} with mentor-guided exercises.`,
      estimatedDays: 4,
    });
  }
  return items;
}

function detectHeadline(text: string): string {
  const summary = text.match(/SUMMARY[\s\S]*?(?=EXPERIENCE|SKILLS|$)/i);
  if (summary) {
    const line = summary[0].split('\n').find((l) => l.trim().length > 40);
    if (line) return line.trim().slice(0, 200);
  }
  const firstLine = text.split('\n').find((l) => l.trim().length > 20);
  return firstLine?.trim().slice(0, 200) ?? 'Professional profile';
}

export function analyzeResumeText(text: string, targetRole?: SimRole): ResumeAnalysis {
  const normalized = text.trim();
  if (normalized.length < 80) {
    throw new Error('Resume text is too short. Paste or upload a fuller resume.');
  }

  const skills = extractSkills(normalized);
  const experienceYears = extractExperienceYears(normalized);
  const experienceSummary = extractExperienceBullets(normalized);
  const projects = extractProjects(normalized);
  const headline = detectHeadline(normalized);

  const jobMatchScores = SIM_ROLES.map((role) => {
    const { score, rationale } = scoreRole(role.id, skills, experienceYears);
    return { role: role.id, label: role.label, score, rationale };
  }).sort((a, b) => b.score - a.score);

  const suggestedRoles = jobMatchScores.slice(0, 2).map((j) => j.role);
  const topRole = targetRole ?? suggestedRoles[0] ?? 'qa_tester';

  const weights = ROLE_SKILL_WEIGHTS[topRole];
  const skillSet = new Set(skills.map((s) => s.toLowerCase()));
  const gaps = weights.required.filter((r) => !hasSkill(skillSet, r));

  const strengths: string[] = [];
  if (experienceYears) strengths.push(`${experienceYears}+ years of relevant experience detected`);
  if (projects.length > 0) strengths.push(`${projects.length} portfolio/project entries found`);
  if (skills.length >= 6) strengths.push(`Broad skill set (${skills.length} items identified)`);
  if (strengths.length === 0) strengths.push('Clear motivation to transition — good base to build on');

  const practiceProjects = PRACTICE_BY_ROLE[topRole].map((p) => ({
    ...p,
    role: topRole,
  }));

  return {
    skills,
    experienceYears,
    experienceSummary,
    projects,
    suggestedRoles,
    jobMatchScores,
    learningRoadmap: buildRoadmap(topRole, gaps),
    practiceProjects,
    strengths,
    gaps: gaps.slice(0, 5),
    headline,
  };
}
