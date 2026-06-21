import type {
  ProgressDashboard,
  ProgressLearningStep,
  ProgressModuleSummary,
  ProgressNextStep,
  ProgressWeakArea,
  SimRole,
} from '@career-sim/shared';
import { SIM_ROLES } from '@career-sim/shared';
import { listSimulationModules } from '../data/simulations';
import { getLatestJobMatch } from '../repositories/job-repository';
import { getLatestAnalysis } from '../repositories/resume-repository';
import { listSessionsForUser } from '../repositories/simulation-repository';

const TOTAL_MODULES = 4;
const TASKS_PER_MODULE = 4;
const TOTAL_SIM_TASKS = TOTAL_MODULES * TASKS_PER_MODULE;

const ROLE_PRACTICE_SKILLS: Record<SimRole, string[]> = {
  qa_tester: ['Manual Testing', 'Test Cases', 'Bug Reporting', 'Regression Testing'],
  data_analyst: ['SQL', 'Python', 'Excel', 'Data Analysis'],
  project_manager: ['Agile/Scrum', 'Project Planning', 'Risk Management', 'Stakeholder Communication'],
  ai_reviewer: ['Quality Review', 'Critical Thinking', 'Feedback Writing', 'AI Safety'],
};

function readinessLabel(score: number): ProgressDashboard['readiness']['label'] {
  if (score < 25) return 'Getting started';
  if (score < 55) return 'Building skills';
  if (score < 80) return 'Interview ready';
  return 'Job ready';
}

function computeReadiness(input: {
  resumeTopScore: number | null;
  jobMatchScore: number | null;
  simulationPercent: number;
}): { score: number; breakdown: ProgressDashboard['readiness']['breakdown'] } {
  const weights: { value: number; weight: number }[] = [];

  if (input.resumeTopScore !== null) weights.push({ value: input.resumeTopScore, weight: 0.25 });
  if (input.jobMatchScore !== null) weights.push({ value: input.jobMatchScore, weight: 0.35 });
  weights.push({ value: input.simulationPercent, weight: 0.4 });

  const totalWeight = weights.reduce((s, w) => s + w.weight, 0);
  const score =
    totalWeight > 0
      ? Math.round(weights.reduce((s, w) => s + w.value * (w.weight / totalWeight), 0))
      : 0;

  return {
    score,
    breakdown: {
      resumeMatch: input.resumeTopScore,
      jobMatch: input.jobMatchScore,
      simulationProgress: input.simulationPercent,
    },
  };
}

function buildModuleSummaries(
  sessions: Awaited<ReturnType<typeof listSessionsForUser>>,
): ProgressModuleSummary[] {
  const byRole = new Map(sessions.map((s) => [s.roleId, s]));

  return SIM_ROLES.map((role) => {
    const session = byRole.get(role.id);
    if (!session) {
      return {
        roleId: role.id,
        label: role.label,
        status: 'not_started' as const,
        progressPercent: 0,
        tasksCompleted: 0,
        totalTasks: TASKS_PER_MODULE,
      };
    }
    return {
      roleId: role.id,
      label: role.label,
      status: session.status === 'completed' ? 'completed' : 'in_progress',
      progressPercent: session.progressPercent,
      tasksCompleted: session.tasksCompleted,
      totalTasks: session.totalTasks,
    };
  });
}

function buildWeakAreas(
  resumeGaps: string[],
  jobGaps: string[],
  missingTools: string[],
  sessions: Awaited<ReturnType<typeof listSessionsForUser>>,
): ProgressWeakArea[] {
  const areas: ProgressWeakArea[] = [];

  for (const gap of resumeGaps.slice(0, 3)) {
    areas.push({ id: `resume-${gap}`, label: gap, source: 'resume', detail: 'Identified from resume analysis' });
  }
  for (const gap of jobGaps.slice(0, 5)) {
    if (!areas.some((a) => a.label === gap)) {
      areas.push({ id: `job-${gap}`, label: gap, source: 'job_match', detail: 'Required by your target job' });
    }
  }
  for (const tool of missingTools.slice(0, 3)) {
    areas.push({
      id: `tool-${tool}`,
      label: tool,
      source: 'tools',
      detail: 'Tool mentioned in job posting but not on resume',
    });
  }

  for (const session of sessions) {
    const mod = listSimulationModules().find((m) => m.roleId === session.roleId);
    for (const tp of session.tasks) {
      if (tp.status === 'needs_revision') {
        areas.push({
          id: `sim-${session.roleId}-${tp.taskId}`,
          label: `${mod?.label ?? session.roleId} task needs revision`,
          source: 'simulation',
          detail: tp.score !== null ? `Last score: ${tp.score}%` : undefined,
        });
      }
    }
  }

  return areas.slice(0, 10);
}

function buildLearningPath(
  steps: { step: number; title: string; description: string; estimatedDays: number }[],
  hasResume: boolean,
  hasJob: boolean,
  tasksDone: number,
): ProgressLearningStep[] {
  if (!steps.length) return [];

  let currentIdx = 0;
  if (hasResume) currentIdx = 1;
  if (hasJob) currentIdx = 2;
  if (tasksDone > 0) currentIdx = Math.min(3, steps.length - 1);
  if (tasksDone >= 4) currentIdx = Math.min(4, steps.length - 1);

  return steps.map((s, i) => ({
    ...s,
    status: i < currentIdx ? 'done' : i === currentIdx ? 'current' : 'upcoming',
  }));
}

function buildNextSteps(input: {
  hasResume: boolean;
  hasJob: boolean;
  tasksDone: number;
  modulesCompleted: number;
  weakAreas: ProgressWeakArea[];
  activeRole: SimRole | null;
  topRole: SimRole | null;
  jobInferredRole: SimRole | null;
}): ProgressNextStep[] {
  const steps: ProgressNextStep[] = [];

  if (!input.hasResume) {
    steps.push({
      id: 'upload-resume',
      title: 'Upload your resume',
      description: 'We extract skills, experience, and a personalized learning roadmap.',
      href: '/resume',
      priority: 'high',
    });
    return steps;
  }

  if (!input.hasJob) {
    steps.push({
      id: 'match-job',
      title: 'Match a job description',
      description: 'Paste a real posting to see skill gaps and a targeted learning path.',
      href: '/job',
      priority: 'high',
    });
  }

  const revision = input.weakAreas.find((w) => w.source === 'simulation');
  if (revision && input.activeRole) {
    steps.push({
      id: 'revise-task',
      title: 'Revise your simulation submission',
      description: revision.detail ?? 'Improve your score to unlock the next task.',
      href: `/roles/${input.activeRole}`,
      priority: 'high',
    });
  }

  if (input.activeRole && input.tasksDone > 0 && input.modulesCompleted < TOTAL_MODULES) {
    steps.push({
      id: 'continue-sim',
      title: 'Continue your simulation',
      description: 'Pick up where you left off — real company-style tasks with instant feedback.',
      href: `/roles/${input.activeRole}`,
      priority: 'high',
    });
  }

  if (input.tasksDone === 0) {
    const role = input.jobInferredRole ?? input.topRole ?? 'qa_tester';
    const label = SIM_ROLES.find((r) => r.id === role)?.label ?? 'QA Tester';
    steps.push({
      id: 'start-sim',
      title: `Start ${label} simulation`,
      description: 'Practice real work tasks — test cases, reports, plans, or AI reviews.',
      href: `/roles/${role}`,
      priority: 'high',
    });
  }

  const topGap = input.weakAreas.find((w) => w.source === 'job_match' || w.source === 'resume');
  if (topGap && steps.length < 4) {
    steps.push({
      id: 'practice-gap',
      title: `Strengthen: ${topGap.label}`,
      description: 'Ask your AI mentor to explain this topic with examples, then practice in a simulation.',
      href: '/roles',
      priority: 'medium',
    });
  }

  if (input.modulesCompleted < TOTAL_MODULES && steps.length < 4) {
    steps.push({
      id: 'explore-roles',
      title: 'Try another role simulation',
      description: `${input.modulesCompleted}/${TOTAL_MODULES} modules complete — broaden your practice.`,
      href: '/roles',
      priority: 'medium',
    });
  }

  if (input.hasResume && steps.length < 4) {
    steps.push({
      id: 'generate-portfolio',
      title: 'Generate your portfolio',
      description: 'Auto-build resume bullets, LinkedIn copy, and GitHub README from your work.',
      href: '/portfolio',
      priority: input.modulesCompleted >= 1 ? 'high' : 'medium',
    });
  }

  if (input.modulesCompleted === TOTAL_MODULES) {
    const existing = steps.find((s) => s.id === 'generate-portfolio');
    if (!existing) {
      steps.unshift({
        id: 'generate-portfolio',
        title: 'Generate your portfolio',
        description: 'All simulations done — turn your practice into resume-ready artifacts.',
        href: '/portfolio',
        priority: 'high',
      });
    }
  }

  if (steps.length < 4) {
    steps.push({
      id: 'mock-interview',
      title: 'Practice a mock interview',
      description: 'Behavioral and technical questions with instant AI feedback and scoring.',
      href: '/interview',
      priority: input.tasksDone > 0 ? 'medium' : 'low',
    });
  }

  if (steps.length < 3) {
    steps.push({
      id: 'mentor',
      title: 'Chat with your AI mentor',
      description: 'Ask anything in plain English — sidebar on desktop, bot icon on mobile.',
      href: '/dashboard',
      priority: 'low',
    });
  }

  return steps.slice(0, 5);
}

export async function buildProgressDashboard(userId: string, fullName: string): Promise<ProgressDashboard> {
  const latest = await getLatestAnalysis(userId);
  const latestJob = await getLatestJobMatch(userId);
  const sessions = await listSessionsForUser(userId);

  const modules = buildModuleSummaries(sessions);
  const tasksCompleted = sessions.reduce((s, sess) => s + sess.tasksCompleted, 0);
  const modulesCompleted = sessions.filter((s) => s.status === 'completed').length;
  const modulesInProgress = sessions.filter((s) => s.status === 'in_progress').length;
  const simulationPercent = Math.round((tasksCompleted / TOTAL_SIM_TASKS) * 100);
  const projectCompletionPercent = Math.round(
    modules.reduce((s, m) => s + m.progressPercent, 0) / TOTAL_MODULES,
  );

  const resumeTopScore = latest?.analysis.jobMatchScores[0]?.score ?? null;
  const jobMatchScore = latestJob?.analysis.overallMatchScore ?? null;
  const readiness = computeReadiness({
    resumeTopScore,
    jobMatchScore,
    simulationPercent,
  });

  const practicedSkills = new Set<string>();
  for (const session of sessions) {
    if (session.tasksCompleted > 0) {
      const roleSkills = ROLE_PRACTICE_SKILLS[session.roleId];
      const count = Math.min(session.tasksCompleted, roleSkills.length);
      roleSkills.slice(0, count).forEach((sk) => practicedSkills.add(sk));
    }
  }

  const skillsFromResume = latest?.analysis.skills ?? [];
  const matchedFromJob = latestJob?.analysis.matchedSkills ?? [];
  const skillsLearned = [...new Set([...skillsFromResume, ...matchedFromJob, ...practicedSkills])].slice(0, 20);

  const weakAreas = buildWeakAreas(
    latest?.analysis.gaps ?? [],
    latestJob?.analysis.skillGaps ?? [],
    latestJob?.analysis.missingTools ?? [],
    sessions,
  );

  const activeSession = sessions.find((s) => s.status === 'in_progress');
  const activeRole = activeSession?.roleId ?? null;

  const nextSteps = buildNextSteps({
    hasResume: Boolean(latest),
    hasJob: Boolean(latestJob),
    tasksDone: tasksCompleted,
    modulesCompleted,
    weakAreas,
    activeRole,
    topRole: latest?.analysis.jobMatchScores[0]?.role ?? null,
    jobInferredRole: latestJob?.analysis.inferredRole ?? null,
  });

  const learningPath = buildLearningPath(
    latestJob?.analysis.learningPath ?? latest?.analysis.learningRoadmap ?? [],
    Boolean(latest),
    Boolean(latestJob),
    tasksCompleted,
  );

  let nextStepMessage = nextSteps[0]?.description ?? 'Explore the platform';
  if (tasksCompleted > 0 && modulesCompleted < TOTAL_MODULES) {
    nextStepMessage = 'Keep building — finish simulations to raise your readiness score';
  } else if (modulesCompleted === TOTAL_MODULES) {
    nextStepMessage = 'Generate your portfolio — resume bullets, LinkedIn, and GitHub README';
  }

  return {
    phase: 10,
    message: `Welcome back, ${fullName.split(' ')[0]}!`,
    readiness: {
      score: readiness.score,
      label: readinessLabel(readiness.score),
      breakdown: readiness.breakdown,
    },
    stats: {
      skillsIdentified: skillsFromResume.length,
      skillsPracticed: practicedSkills.size,
      tasksCompleted,
      totalSimulationTasks: TOTAL_SIM_TASKS,
      modulesCompleted,
      totalModules: TOTAL_MODULES,
      projectCompletionPercent,
      modulesInProgress,
    },
    skillsLearned,
    weakAreas,
    nextSteps,
    modules,
    learningPath,
    resume: latest
      ? {
          id: latest.id,
          headline: latest.analysis.headline,
          topRole: latest.analysis.jobMatchScores[0]?.label ?? null,
          topScore: latest.analysis.jobMatchScores[0]?.score ?? null,
        }
      : null,
    jobMatch: latestJob
      ? {
          id: latestJob.id,
          jobTitle: latestJob.jobTitle,
          matchScore: latestJob.analysis.overallMatchScore,
          gapCount: latestJob.analysis.skillGaps.length,
        }
      : null,
    activeSimulation: activeSession
      ? {
          roleId: activeSession.roleId,
          label: SIM_ROLES.find((r) => r.id === activeSession.roleId)?.label ?? activeSession.roleId,
          progressPercent: activeSession.progressPercent,
          tasksCompleted: activeSession.tasksCompleted,
          totalTasks: activeSession.totalTasks,
        }
      : null,
  };
}
