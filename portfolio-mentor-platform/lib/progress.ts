const STORAGE_KEY = 'resume-mentor-progress-v1';

export type ProgressState = {
  completedSteps: Record<string, string[]>;
  /** projectSlug → stepId → checked checklist item strings */
  checklists: Record<string, Record<string, string[]>>;
  notes: Record<string, string>;
  mentorMessages: Record<string, MentorMessage[]>;
  lastVisited?: string;
};

export type MentorMessage = {
  id: string;
  role: 'user' | 'mentor';
  content: string;
  createdAt: string;
};

const defaultState: ProgressState = {
  completedSteps: {},
  checklists: {},
  notes: {},
  mentorMessages: {},
};

export function loadProgress(): ProgressState {
  if (typeof window === 'undefined') return defaultState;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState;
    return { ...defaultState, ...JSON.parse(raw) };
  } catch {
    return defaultState;
  }
}

export function saveProgress(state: ProgressState): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function toggleChecklistItem(
  state: ProgressState,
  projectSlug: string,
  stepId: string,
  item: string,
): ProgressState {
  const project = state.checklists[projectSlug] ?? {};
  const current = new Set(project[stepId] ?? []);
  if (current.has(item)) current.delete(item);
  else current.add(item);
  return {
    ...state,
    checklists: {
      ...state.checklists,
      [projectSlug]: {
        ...project,
        [stepId]: [...current],
      },
    },
    lastVisited: projectSlug,
  };
}

export function getChecklist(
  state: ProgressState,
  projectSlug: string,
  stepId: string,
): string[] {
  return state.checklists[projectSlug]?.[stepId] ?? [];
}

export function toggleStep(
  state: ProgressState,
  projectSlug: string,
  stepId: string,
): ProgressState {
  const current = new Set(state.completedSteps[projectSlug] ?? []);
  if (current.has(stepId)) current.delete(stepId);
  else current.add(stepId);
  return {
    ...state,
    completedSteps: {
      ...state.completedSteps,
      [projectSlug]: [...current],
    },
    lastVisited: projectSlug,
  };
}

export function setNote(
  state: ProgressState,
  projectSlug: string,
  note: string,
): ProgressState {
  return {
    ...state,
    notes: { ...state.notes, [projectSlug]: note },
    lastVisited: projectSlug,
  };
}

export function appendMentorMessage(
  state: ProgressState,
  projectSlug: string,
  message: Omit<MentorMessage, 'id' | 'createdAt'>,
): ProgressState {
  const entry: MentorMessage = {
    ...message,
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
  };
  const thread = state.mentorMessages[projectSlug] ?? [];
  return {
    ...state,
    mentorMessages: {
      ...state.mentorMessages,
      [projectSlug]: [...thread, entry],
    },
    lastVisited: projectSlug,
  };
}

export function projectProgress(
  state: ProgressState,
  projectSlug: string,
  stepIds: string[],
): number {
  if (stepIds.length === 0) return 0;
  const done = state.completedSteps[projectSlug]?.length ?? 0;
  return Math.round((done / stepIds.length) * 100);
}

export function overallProgress(
  state: ProgressState,
  projects: { slug: string; stepCount: number }[],
): number {
  const total = projects.reduce((s, p) => s + p.stepCount, 0);
  if (total === 0) return 0;
  const done = projects.reduce(
    (s, p) => s + (state.completedSteps[p.slug]?.length ?? 0),
    0,
  );
  return Math.round((done / total) * 100);
}
