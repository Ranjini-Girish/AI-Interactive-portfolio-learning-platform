import type { Step } from '@/data/curriculum';

export type NarrationSegment = {
  id: string;
  kind: 'intro' | 'instruction' | 'hint' | 'checklist' | 'outro';
  label: string;
  text: string;
};

export function buildStepNarration(
  projectTitle: string,
  step: Step,
  stepNumber: number,
  totalSteps: number,
): NarrationSegment[] {
  const segments: NarrationSegment[] = [
    {
      id: 'intro',
      kind: 'intro',
      label: 'Introduction',
      text: `Let's work on ${projectTitle}. Step ${stepNumber} of ${totalSteps}: ${step.title}.`,
    },
    {
      id: 'instruction',
      kind: 'instruction',
      label: 'What to build',
      text: step.instruction,
    },
  ];

  if (step.hint) {
    segments.push({
      id: 'hint',
      kind: 'hint',
      label: 'Hint',
      text: `Hint: ${step.hint}`,
    });
  }

  if (step.verifyChecklist.length > 0) {
    segments.push({
      id: 'checklist-intro',
      kind: 'checklist',
      label: 'Checklist intro',
      text: `You have ${step.verifyChecklist.length} verification items. Test each one in your running app before checking it off.`,
    });
    step.verifyChecklist.forEach((item, i) => {
      segments.push({
        id: `checklist-${i}`,
        kind: 'checklist',
        label: `Checklist ${i + 1}`,
        text: `Item ${i + 1}: ${item}`,
      });
    });
  }

  segments.push({
    id: 'outro',
    kind: 'outro',
    label: 'Wrap-up',
    text:
      'When you finish, use Get mentor feedback for a review, or mark the step complete and move on. Say "next segment" to skip ahead, or "repeat" to hear this again.',
  });

  return segments;
}

/** Strip markdown for speech. */
export function textForSpeech(raw: string): string {
  return raw
    .replace(/\*\*/g, '')
    .replace(/\[(.*?)\]\(.*?\)/g, '$1')
    .replace(/#{1,6}\s/g, '')
    .replace(/`/g, '')
    .replace(/\n+/g, '. ')
    .trim();
}

export function stepNumberFor(project: { milestones: { steps: { id: string }[] }[] }, stepId: string): {
  index: number;
  total: number;
} {
  const all = project.milestones.flatMap((m) => m.steps);
  const index = all.findIndex((s) => s.id === stepId);
  return { index: index >= 0 ? index + 1 : 1, total: all.length };
}
