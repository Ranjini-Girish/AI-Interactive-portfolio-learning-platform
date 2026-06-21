import type { JobMatchAnalysis, SimRole } from '@career-sim/shared';
import type { ResumeAnalysis } from '@career-sim/shared';
import {
  extractJobTitle,
  extractSkillsFromText,
  extractToolsFromText,
  inferRoleFromText,
  skillsMatch,
} from './skill-taxonomy';

const GAP_LEARNING: Record<string, { title: string; description: string; days: number }> = {
  Selenium: {
    title: 'Intro to Selenium automation',
    description: 'Record and run 3 basic UI tests; understand locators and waits.',
    days: 5,
  },
  Cypress: {
    title: 'Cypress quick start',
    description: 'Write end-to-end tests for a sample login flow in plain JavaScript.',
    days: 4,
  },
  'Power BI': {
    title: 'Build your first Power BI report',
    description: 'Connect CSV data, create 2 charts, and publish a one-page dashboard.',
    days: 4,
  },
  Tableau: {
    title: 'Tableau fundamentals',
    description: 'Drag-and-drop charts from a sample dataset; explain one insight aloud.',
    days: 4,
  },
  Postman: {
    title: 'API testing with Postman',
    description: 'Send GET/POST requests, save a collection, and assert status codes.',
    days: 2,
  },
  Jira: {
    title: 'Jira for testers & coordinators',
    description: 'Create issues, link to sprints, and write clear acceptance criteria.',
    days: 2,
  },
  Python: {
    title: 'Python for data & automation',
    description: 'Complete a pandas mini-lab: load CSV, filter rows, export summary.',
    days: 5,
  },
  SQL: {
    title: 'SQL practice sprint',
    description: 'Write SELECT, JOIN, and GROUP BY queries on a sample database.',
    days: 4,
  },
  Git: {
    title: 'Git basics for team work',
    description: 'Clone, branch, commit, and open a pull request on a practice repo.',
    days: 2,
  },
};

function defaultGapStep(gap: string, index: number): JobMatchAnalysis['learningPath'][number] {
  return {
    step: index + 1,
    title: `Learn: ${gap}`,
    description: `Practice ${gap} with mentor-guided exercises tied to real job tasks.`,
    estimatedDays: 3,
  };
}

function buildLearningPath(gaps: string[], missingTools: string[]): JobMatchAnalysis['learningPath'] {
  const items: JobMatchAnalysis['learningPath'] = [];
  let step = 1;

  for (const tool of missingTools.slice(0, 3)) {
    const preset = GAP_LEARNING[tool];
    items.push({
      step: step++,
      title: preset?.title ?? `Tool practice: ${tool}`,
      description: preset?.description ?? `Get hands-on with ${tool} using lab exercises.`,
      estimatedDays: preset?.days ?? 3,
    });
  }

  for (const gap of gaps.slice(0, 4)) {
    if (items.some((i) => i.title.toLowerCase().includes(gap.toLowerCase()))) continue;
    const preset = GAP_LEARNING[gap];
    items.push(
      preset
        ? { step: step++, title: preset.title, description: preset.description, estimatedDays: preset.days }
        : { ...defaultGapStep(gap, step - 1), step: step++ },
    );
  }

  if (items.length === 0) {
    items.push({
      step: 1,
      title: 'Interview prep for this role',
      description: 'Practice explaining your projects and run a mock simulation module.',
      estimatedDays: 3,
    });
  }

  return items.slice(0, 6);
}

function splitRequiredPreferred(allSkills: string[], jdText: string): {
  required: string[];
  preferred: string[];
} {
  const niceBlock = jdText.match(/nice to have[\s\S]*?(?=benefits|about|apply|$)/i);
  const preferred = new Set<string>();

  if (niceBlock) {
    extractSkillsFromText(niceBlock[0]).forEach((s) => preferred.add(s));
  }

  const required = allSkills.filter((s) => !preferred.has(s));
  return {
    required: required.length > 0 ? required : allSkills,
    preferred: [...preferred].filter((s) => !required.includes(s)),
  };
}

export function matchJobToResume(
  jdText: string,
  resume: ResumeAnalysis,
  targetRole?: SimRole,
): JobMatchAnalysis {
  const normalized = jdText.trim();
  if (normalized.length < 60) {
    throw new Error('Job description is too short. Paste the full posting.');
  }

  const jobTitle = extractJobTitle(normalized);
  const inferredRole = targetRole ?? inferRoleFromText(normalized);
  const allJdSkills = extractSkillsFromText(normalized);
  const { required, preferred } = splitRequiredPreferred(allJdSkills, normalized);
  const toolsMentioned = extractToolsFromText(normalized);

  const resumeSkills = resume.skills;
  const allRequired = [...new Set([...required, ...toolsMentioned])];

  const matchedSkills = allRequired.filter((req) =>
    resumeSkills.some((rs) => skillsMatch(rs, req)),
  );

  const skillGaps = allRequired.filter(
    (req) => !resumeSkills.some((rs) => skillsMatch(rs, req)),
  );

  const missingTools = toolsMentioned.filter(
    (tool) => !resumeSkills.some((rs) => skillsMatch(rs, tool)),
  );

  const preferredMatched = preferred.filter((p) =>
    resumeSkills.some((rs) => skillsMatch(rs, p)),
  );

  const requiredScore =
    allRequired.length > 0 ? (matchedSkills.length / allRequired.length) * 85 : 50;
  const preferredBonus =
    preferred.length > 0 ? (preferredMatched.length / preferred.length) * 15 : 10;
  const overallMatchScore = Math.min(99, Math.round(requiredScore + preferredBonus));

  const learningPath = buildLearningPath(skillGaps, missingTools);

  const plainSummary =
    overallMatchScore >= 75
      ? `Strong fit for "${jobTitle}". You already cover ${matchedSkills.length} of ${allRequired.length} key requirements. Focus on polishing stories for interviews.`
      : overallMatchScore >= 50
        ? `Moderate fit for "${jobTitle}". You have a solid base (${matchedSkills.length} matches) but should close ${skillGaps.length} gaps before applying.`
        : `Early-stage fit for "${jobTitle}". Treat this as a learning target — follow the path below to build missing skills over the next few weeks.`;

  return {
    jobTitle,
    inferredRole,
    requiredSkills: required,
    preferredSkills: preferred,
    toolsMentioned,
    resumeSkills,
    matchedSkills,
    skillGaps,
    missingTools,
    overallMatchScore,
    learningPath,
    plainSummary,
  };
}
