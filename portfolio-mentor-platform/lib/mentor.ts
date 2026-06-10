import type { Project, Step } from '@/data/curriculum';

export type MentorRequest = {
  projectSlug: string;
  projectTitle: string;
  step: Step;
  userMessage: string;
  completedChecklist: string[];
  note?: string;
};

export type MentorResponse = {
  reply: string;
  feedback: {
    strengths: string[];
    gaps: string[];
    nextAction: string;
  };
  checklistReview: { item: string; status: 'pass' | 'review' | 'missing' }[];
};

export function buildLocalMentorReply(req: MentorRequest): MentorResponse {
  const done = req.completedChecklist.length;
  const total = req.step.verifyChecklist.length;
  const ratio = total > 0 ? done / total : 0;

  const checklistReview = req.step.verifyChecklist.map((item) => {
    const hit = req.completedChecklist.some(
      (c) => c.toLowerCase() === item.toLowerCase(),
    );
    return { item, status: hit ? ('pass' as const) : ('missing' as const) };
  });

  const strengths: string[] = [];
  const gaps: string[] = [];

  if (ratio >= 1) {
    strengths.push('All verification items checked — ready to mark this step complete.');
  } else if (ratio >= 0.5) {
    strengths.push('Solid partial progress on this step.');
    gaps.push(`Finish remaining checklist items (${done}/${total} done).`);
  } else {
    gaps.push('Start with the first checklist item before expanding scope.');
  }

  if (req.userMessage.length > 20) {
    strengths.push('You asked a specific question — good engineering habit.');
  } else {
    gaps.push('Add detail: file paths, errors, or screenshots in your mentor question.');
  }

  const replyParts = [
    `**${req.step.title}** — mentor review for *${req.projectTitle}*`,
    '',
    req.step.hint ? `💡 Hint: ${req.step.hint}` : '',
    '',
    `Checklist: ${done}/${total} items marked done.`,
    '',
    ratio >= 1
      ? '✅ Looks complete. Mark the step done and move to the next one. Update README as you go.'
      : '🛠 Focus on one unchecked item next. Run your app and verify behavior before checking boxes.',
    '',
    req.userMessage
      ? `On your question: break it into (1) expected behavior, (2) what you see, (3) smallest next experiment.`
      : 'Tip: paste errors or branch names when you ask for help.',
  ].filter(Boolean);

  return {
    reply: replyParts.join('\n'),
    feedback: {
      strengths,
      gaps,
      nextAction:
        ratio >= 1
          ? 'Mark step complete and open the next step.'
          : checklistReview.find((c) => c.status === 'missing')?.item ??
            'Re-read the step instruction and implement the smallest slice.',
    },
    checklistReview,
  };
}

export function buildStepContext(project: Project, stepId: string): Step | undefined {
  for (const m of project.milestones) {
    const step = m.steps.find((s) => s.id === stepId);
    if (step) return step;
  }
  return undefined;
}
