/** Shared skill & tool patterns for resume + job description analysis */

import type { SimRole } from '@career-sim/shared';

export const SKILL_PATTERNS: { skill: string; patterns: RegExp[] }[] = [
  { skill: 'Manual Testing', patterns: [/manual test/i, /manual testing/i] },
  { skill: 'Test Cases', patterns: [/test case/i, /test scripts/i, /test plan/i] },
  { skill: 'Bug Reporting', patterns: [/bug report/i, /defect/i, /logged defects/i] },
  { skill: 'Jira', patterns: [/\bjira\b/i] },
  { skill: 'Postman', patterns: [/\bpostman\b/i] },
  { skill: 'Regression Testing', patterns: [/regression/i] },
  { skill: 'Agile/Scrum', patterns: [/\bagile\b/i, /\bscrum\b/i, /standup/i, /sprint/i] },
  { skill: 'SQL', patterns: [/\bsql\b/i, /postgresql/i, /mysql/i] },
  { skill: 'Python', patterns: [/\bpython\b/i, /\bpandas\b/i] },
  { skill: 'Excel', patterns: [/\bexcel\b/i] },
  { skill: 'Tableau', patterns: [/\btableau\b/i] },
  { skill: 'Power BI', patterns: [/power bi/i, /powerbi/i] },
  { skill: 'Data Cleaning', patterns: [/data clean/i, /missing values/i, /duplicates/i] },
  { skill: 'Visualization', patterns: [/chart/i, /dashboard/i, /visual/i] },
  { skill: 'Statistics', patterns: [/statistic/i, /regression model/i] },
  { skill: 'Project Planning', patterns: [/project plan/i, /timeline/i, /milestone/i] },
  { skill: 'Risk Management', patterns: [/risk/i] },
  { skill: 'Stakeholder Communication', patterns: [/stakeholder/i, /status report/i, /leadership/i] },
  { skill: 'Microsoft Project', patterns: [/microsoft project/i, /smartsheet/i] },
  { skill: 'UAT Coordination', patterns: [/\buat\b/i, /user acceptance/i] },
  { skill: 'Git', patterns: [/\bgit\b/i, /github/i] },
  { skill: 'API Testing', patterns: [/api test/i, /api smoke/i, /postman/i] },
  { skill: 'Selenium', patterns: [/selenium/i] },
  { skill: 'Cypress', patterns: [/cypress/i] },
  { skill: 'Attention to Detail', patterns: [/attention to detail/i] },
  { skill: 'AI Evaluation', patterns: [/\bai\b/i, /hallucin/i, /llm/i, /prompt/i, /machine learning/i] },
  { skill: 'Communication', patterns: [/communication skills/i, /written and verbal/i] },
  { skill: 'Documentation', patterns: [/documentation/i, /technical writing/i] },
];

export const TOOL_PATTERNS: { tool: string; patterns: RegExp[] }[] = [
  { tool: 'Jira', patterns: [/\bjira\b/i] },
  { tool: 'Postman', patterns: [/\bpostman\b/i] },
  { tool: 'Selenium', patterns: [/selenium/i] },
  { tool: 'Cypress', patterns: [/cypress/i] },
  { tool: 'Tableau', patterns: [/\btableau\b/i] },
  { tool: 'Power BI', patterns: [/power bi/i] },
  { tool: 'Excel', patterns: [/\bexcel\b/i] },
  { tool: 'Python', patterns: [/\bpython\b/i] },
  { tool: 'SQL', patterns: [/\bsql\b/i] },
  { tool: 'Git', patterns: [/\bgit\b/i] },
  { tool: 'Confluence', patterns: [/confluence/i] },
  { tool: 'Microsoft Project', patterns: [/microsoft project/i] },
  { tool: 'Smartsheet', patterns: [/smartsheet/i] },
  { tool: 'TestRail', patterns: [/testrail/i] },
  { tool: 'Azure DevOps', patterns: [/azure devops/i, /ado\b/i] },
];

export function normalizeSkillToken(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9/+ ]/g, '').trim();
}

export function skillsMatch(resumeSkill: string, required: string): boolean {
  const a = normalizeSkillToken(resumeSkill);
  const b = normalizeSkillToken(required);
  if (!a || !b) return false;
  return a.includes(b) || b.includes(a);
}

export function extractSkillsFromText(text: string): string[] {
  const found = new Set<string>();
  for (const { skill, patterns } of SKILL_PATTERNS) {
    if (patterns.some((p) => p.test(text))) found.add(skill);
  }

  const reqBlock = text.match(
    /(?:requirements|qualifications|must have|required skills|what you bring)[\s\S]*?(?=responsibilities|about us|benefits|nice to have|$)/i,
  );
  const scanText = reqBlock ? reqBlock[0] : text;

  scanText
    .split(/[,•|\n;]/)
    .map((s) => s.trim())
    .filter((s) => s.length > 2 && s.length < 50)
    .forEach((raw) => {
      const cleaned = raw.replace(/^[\d.)+\-\s]+/, '').trim();
      if (cleaned.length > 2 && !/^(years?|experience|degree|bachelor|master)/i.test(cleaned)) {
        found.add(cleaned);
      }
    });

  return [...found].slice(0, 30);
}

export function extractToolsFromText(text: string): string[] {
  const found = new Set<string>();
  for (const { tool, patterns } of TOOL_PATTERNS) {
    if (patterns.some((p) => p.test(text))) found.add(tool);
  }
  return [...found];
}

export function inferRoleFromText(text: string): SimRole {
  const lower = text.toLowerCase();
  if (/data analyst|business analyst|analytics|sql|tableau|power bi/.test(lower)) return 'data_analyst';
  if (/project manager|program manager|scrum master|project coordinator|pmo/.test(lower)) {
    return 'project_manager';
  }
  if (/ai reviewer|ml engineer|prompt engineer|llm|machine learning/.test(lower)) return 'ai_reviewer';
  if (/qa|quality assurance|test engineer|tester|sdet/.test(lower)) return 'qa_tester';
  return 'qa_tester';
}

export function extractJobTitle(text: string): string {
  const titleLine = text.split('\n').find((l) => l.trim().length > 5 && l.trim().length < 80);
  const roleMatch = text.match(/(?:job title|position|role)\s*[:\-]\s*(.+)/i);
  if (roleMatch) return roleMatch[1].trim().slice(0, 120);
  return titleLine?.trim().slice(0, 120) ?? 'Job posting';
}
