import OpenAI from 'openai';
import { z } from 'zod';
import type { PortfolioContent, PortfolioProject, SimRole } from '@career-sim/shared';
import { SIM_ROLES } from '@career-sim/shared';
import { getSimulationModule } from '../data/simulations';
import { env } from '../config/env';
import { getLatestJobMatch } from '../repositories/job-repository';
import { getLatestAnalysis } from '../repositories/resume-repository';
import { listSessionsForUser } from '../repositories/simulation-repository';
import { getMentorModel, isMentorConfigured } from './mentor-prompt';

const portfolioSchema = z.object({
  headline: z.string(),
  targetRole: z.string(),
  resumeBullets: z.array(z.string()).min(4),
  linkedInHeadline: z.string(),
  linkedInAbout: z.string(),
  projects: z.array(
    z.object({
      title: z.string(),
      role: z.enum(['qa_tester', 'data_analyst', 'project_manager', 'ai_reviewer']),
      company: z.string(),
      summary: z.string(),
      bullets: z.array(z.string()).min(2),
      skillsDemonstrated: z.array(z.string()).min(1),
    }),
  ),
  githubReadme: z.string(),
});

type UserContext = {
  fullName: string;
  resumeHeadline: string;
  skills: string[];
  experienceYears: number | null;
  projects: { name: string; description: string }[];
  topRole: string;
  jobTitle: string | null;
  jobMatchScore: number | null;
  skillGaps: string[];
  simulationWork: {
    roleId: SimRole;
    label: string;
    company: string;
    projectName: string;
    tasksCompleted: number;
    totalTasks: number;
    status: string;
  }[];
};

async function gatherContext(userId: string, fullName: string): Promise<UserContext | null> {
  const resume = await getLatestAnalysis(userId);
  if (!resume) return null;

  const job = await getLatestJobMatch(userId);
  const sessions = await listSessionsForUser(userId);
  const a = resume.analysis;
  const top = a.jobMatchScores[0];

  const simulationWork = sessions.map((s) => {
    const mod = getSimulationModule(s.roleId);
    const label = SIM_ROLES.find((r) => r.id === s.roleId)?.label ?? s.roleId;
    return {
      roleId: s.roleId,
      label,
      company: mod?.company ?? 'Practice Company',
      projectName: mod?.projectName ?? label,
      tasksCompleted: s.tasksCompleted,
      totalTasks: s.totalTasks,
      status: s.status,
    };
  });

  return {
    fullName,
    resumeHeadline: a.headline,
    skills: a.skills,
    experienceYears: a.experienceYears,
    projects: a.projects,
    topRole: top?.label ?? 'Technology Professional',
    jobTitle: job?.jobTitle ?? null,
    jobMatchScore: job?.analysis.overallMatchScore ?? null,
    skillGaps: job?.analysis.skillGaps ?? a.gaps,
    simulationWork,
  };
}

function buildProjectFromSim(
  sim: UserContext['simulationWork'][0],
): PortfolioProject {
  const mod = getSimulationModule(sim.roleId);
  const taskTitles = mod?.tasks.slice(0, sim.tasksCompleted).map((t) => t.title) ?? [];

  const bullets: string[] = [];
  if (sim.roleId === 'qa_tester') {
    bullets.push(
      `Authored manual test cases for ${sim.projectName}, covering happy-path and negative scenarios.`,
      `Logged and prioritized defects with clear reproduction steps for engineering handoff.`,
    );
    if (sim.tasksCompleted >= 3) {
      bullets.push(`Triaged release-blocking bugs and recommended fix order for sprint delivery.`);
    }
  } else if (sim.roleId === 'data_analyst') {
    bullets.push(
      `Analyzed sample sales data to surface revenue trends by region and product line.`,
      `Translated chart findings into executive-ready narrative summaries.`,
    );
  } else if (sim.roleId === 'project_manager') {
    bullets.push(
      `Drafted milestone plan and risk register for ${sim.projectName}.`,
      `Planned two-week sprint backlog with clear acceptance criteria.`,
    );
  } else {
    bullets.push(
      `Reviewed AI-generated customer responses for accuracy, tone, and hallucination risk.`,
      `Authored structured feedback to improve model quality standards.`,
    );
  }

  if (taskTitles.length) {
    bullets.push(`Completed simulation tasks: ${taskTitles.join('; ')}.`);
  }

  return {
    title: sim.projectName,
    role: sim.roleId,
    company: sim.company,
    summary: `Hands-on ${sim.label} simulation at ${sim.company} — practiced real deliverables (${sim.tasksCompleted}/${sim.totalTasks} tasks).`,
    bullets: bullets.slice(0, 4),
    skillsDemonstrated: mod?.tasks.slice(0, 3).map((t) => t.title.split(' ')[0]) ?? [sim.label],
  };
}

export function generateLocalPortfolio(ctx: UserContext): PortfolioContent {
  const targetRole = ctx.jobTitle ?? ctx.topRole;
  const years = ctx.experienceYears;
  const expPhrase = years ? `${years}+ years experience` : 'Career transition professional';

  const resumeBullets: string[] = [];

  if (ctx.skills.length) {
    resumeBullets.push(
      `Applied ${ctx.skills.slice(0, 4).join(', ')} in professional and practice settings aligned to ${targetRole} roles.`,
    );
  }

  for (const sim of ctx.simulationWork.filter((s) => s.tasksCompleted > 0)) {
    const mod = getSimulationModule(sim.roleId);
    resumeBullets.push(
      `Completed ${sim.tasksCompleted} hands-on ${sim.label} simulation tasks for ${mod?.projectName ?? sim.projectName} (${sim.company}).`,
    );
  }

  for (const p of ctx.projects.slice(0, 2)) {
    resumeBullets.push(`Delivered ${p.name}: ${p.description.slice(0, 120)}${p.description.length > 120 ? '…' : ''}`);
  }

  if (ctx.jobMatchScore !== null) {
    resumeBullets.push(
      `Targeted ${targetRole} opportunities with ${ctx.jobMatchScore}% skill alignment; actively closing gaps in ${ctx.skillGaps.slice(0, 3).join(', ') || 'core role skills'}.`,
    );
  }

  while (resumeBullets.length < 5) {
    resumeBullets.push(
      `Collaborated in Agile-style workflows, communicating progress clearly to cross-functional teammates.`,
    );
  }

  const projects: PortfolioProject[] =
    ctx.simulationWork.filter((s) => s.tasksCompleted > 0).map(buildProjectFromSim);

  if (!projects.length && ctx.projects.length) {
    projects.push({
      title: ctx.projects[0].name,
      role: 'qa_tester',
      company: 'Independent Practice',
      summary: ctx.projects[0].description,
      bullets: [
        `Defined scope and outcomes for ${ctx.projects[0].name}.`,
        `Documented results suitable for resume and interview storytelling.`,
      ],
      skillsDemonstrated: ctx.skills.slice(0, 3),
    });
  }

  const linkedInHeadline = `${targetRole} | ${ctx.skills.slice(0, 3).join(' · ')} | ${expPhrase}`;

  const linkedInAbout = `I am building toward ${targetRole} roles with a focus on practical, job-ready skills.

${ctx.resumeHeadline}. Through the Career Transition Simulator I have practiced real company-style deliverables — not just tutorials — including ${ctx.simulationWork.filter((s) => s.tasksCompleted > 0).map((s) => s.label).join(', ') || 'structured learning projects'}.

I am especially interested in opportunities where I can grow in ${ctx.skillGaps.slice(0, 3).join(', ') || 'collaborative team environments'}. Open to connecting with mentors and hiring managers who value clear communication and hands-on learning.`;

  const githubReadme = buildGithubReadme(ctx, projects, targetRole);

  return {
    headline: ctx.resumeHeadline,
    targetRole,
    resumeBullets: resumeBullets.slice(0, 8),
    linkedInHeadline,
    linkedInAbout,
    projects,
    githubReadme,
    provider: 'local',
    generatedAt: new Date().toISOString(),
  };
}

function buildGithubReadme(
  ctx: UserContext,
  projects: PortfolioProject[],
  targetRole: string,
): string {
  const lines = [
    `# ${ctx.fullName} — Portfolio Projects`,
    '',
    `> ${ctx.resumeHeadline}`,
    '',
    `Target role: **${targetRole}**`,
    '',
    '## Skills',
    '',
    ctx.skills.map((s) => `- ${s}`).join('\n'),
    '',
    '## Simulation Projects',
    '',
  ];

  for (const p of projects) {
    lines.push(`### ${p.title}`, `*${p.company} · ${SIM_ROLES.find((r) => r.id === p.role)?.label ?? p.role}*`, '', p.summary, '');
    for (const b of p.bullets) lines.push(`- ${b}`);
    lines.push('');
  }

  lines.push('## Contact', '', 'Generated by AI Career Transition Simulator — portfolio practice artifacts.');
  return lines.join('\n');
}

async function generateOpenAiPortfolio(ctx: UserContext): Promise<PortfolioContent> {
  const client = new OpenAI({ apiKey: env.OPENAI_API_KEY! });
  const model = getMentorModel();

  const prompt = `Generate portfolio content as JSON for this job seeker.

Name: ${ctx.fullName}
Headline: ${ctx.resumeHeadline}
Target role: ${ctx.jobTitle ?? ctx.topRole}
Skills: ${ctx.skills.join(', ')}
Experience years: ${ctx.experienceYears ?? 'unknown'}
Resume projects: ${ctx.projects.map((p) => p.name).join(', ') || 'none'}
Job match: ${ctx.jobMatchScore ?? 'n/a'}%
Skill gaps to acknowledge as growth areas: ${ctx.skillGaps.join(', ') || 'none'}
Simulation work completed:
${ctx.simulationWork.map((s) => `- ${s.label} at ${s.company}: ${s.projectName} (${s.tasksCompleted}/${s.totalTasks} tasks, ${s.status})`).join('\n')}

Return ONLY valid JSON with this shape:
{
  "headline": string,
  "targetRole": string,
  "resumeBullets": string[5-8] (action verbs, metrics where plausible, no fabrication of employers),
  "linkedInHeadline": string (max 120 chars),
  "linkedInAbout": string (3 short paragraphs, first person),
  "projects": [{ "title", "role": qa_tester|data_analyst|project_manager|ai_reviewer, "company", "summary", "bullets": string[2-4], "skillsDemonstrated": string[] }],
  "githubReadme": string (markdown)
}

Rules: Plain English. Base projects on simulation work listed. Do not invent fake companies beyond simulation companies.`;

  const completion = await client.chat.completions.create({
    model,
    messages: [
      { role: 'system', content: 'You output only valid JSON for career portfolio artifacts.' },
      { role: 'user', content: prompt },
    ],
    temperature: 0.6,
    max_tokens: 2000,
    response_format: { type: 'json_object' },
  });

  const raw = completion.choices[0]?.message?.content ?? '{}';
  const parsed = portfolioSchema.parse(JSON.parse(raw));

  return {
    ...parsed,
    provider: 'openai',
    generatedAt: new Date().toISOString(),
  };
}

export function isPortfolioAiConfigured(): boolean {
  return isMentorConfigured();
}

export async function generatePortfolio(
  userId: string,
  fullName: string,
): Promise<PortfolioContent> {
  const ctx = await gatherContext(userId, fullName);
  if (!ctx) {
    throw new Error('Upload or analyze a resume first (Phase 3)');
  }

  if (isMentorConfigured()) {
    try {
      return await generateOpenAiPortfolio(ctx);
    } catch {
      return generateLocalPortfolio(ctx);
    }
  }

  return generateLocalPortfolio(ctx);
}
