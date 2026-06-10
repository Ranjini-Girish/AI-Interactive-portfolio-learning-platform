'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getProject, allStepIds, type Project } from '@/data/curriculum';
import { DOMAIN_LABELS } from '@/lib/beginner-guide';
import { getDemo } from '@/data/demos';
import {
  loadProgress,
  saveProgress,
  toggleStep,
  toggleChecklistItem,
  getChecklist,
  setNote,
  appendMentorMessage,
  projectProgress,
  type ProgressState,
} from '@/lib/progress';
import { buildStepContext } from '@/lib/mentor';
import { MilestoneTracker } from '@/components/MilestoneTracker';
import { StepGuide } from '@/components/StepGuide';
import { MentorPanel } from '@/components/MentorPanel';
import { AudioTutorPanel } from '@/components/AudioTutorPanel';
import { stepNumberFor } from '@/lib/tutor-narration';

export default function ProjectWorkspacePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const [slug, setSlug] = useState<string | null>(null);
  const [project, setProject] = useState<Project | undefined>();
  const [state, setState] = useState<ProgressState>(() => loadProgress());
  const [activeStepId, setActiveStepId] = useState<string>('');
  const [justCompleted, setJustCompleted] = useState(false);

  useEffect(() => {
    params.then(({ slug: s }) => {
      setSlug(s);
      const p = getProject(s);
      setProject(p);
      if (p) {
        const ids = allStepIds(p);
        const saved = loadProgress();
        const firstOpen =
          ids.find((id) => !(saved.completedSteps[s] ?? []).includes(id)) ?? ids[0];
        setActiveStepId(firstOpen ?? '');
      }
    });
  }, [params]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (window.location.hash === '#step-guide') {
      window.setTimeout(() => {
        document.getElementById('step-guide')?.scrollIntoView({ behavior: 'smooth' });
      }, 400);
    }
  }, [slug, activeStepId]);

  const step = useMemo(
    () => (project && activeStepId ? buildStepContext(project, activeStepId) : undefined),
    [project, activeStepId],
  );

  const completed = useMemo(
    () => new Set(state.completedSteps[slug ?? ''] ?? []),
    [state, slug],
  );

  const persist = useCallback((updater: (prev: ProgressState) => ProgressState) => {
    setState((prev) => {
      const next = updater(prev);
      saveProgress(next);
      return next;
    });
  }, []);

  const stepIds = useMemo(() => (project ? allStepIds(project) : []), [project]);
  const checklist = slug && step ? getChecklist(state, slug, step.id) : [];
  const nextStepId = useMemo(() => {
    if (!step) return undefined;
    const idx = stepIds.indexOf(step.id);
    return idx >= 0 && idx < stepIds.length - 1 ? stepIds[idx + 1] : undefined;
  }, [step, stepIds]);

  if (slug && !project) notFound();
  if (!project || !step || !slug) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-16 text-center text-[var(--muted)]">
        Loading workspace…
      </div>
    );
  }

  const demo = getDemo(slug);
  const pct = projectProgress(state, slug, allStepIds(project));
  const messages = state.mentorMessages[slug] ?? [];
  const stepDone = completed.has(step.id);
  const { index: stepNum, total: stepTotal } = stepNumberFor(project, step.id);
  const lastMentorReply = [...messages].reverse().find((m) => m.role === 'mentor')?.content;

  function handleToggleChecklist(item: string) {
    if (!slug || !step) return;
    persist((prev) => toggleChecklistItem(prev, slug, step.id, item));
  }

  function handleToggleStepComplete() {
    if (!slug || !step) return;
    const wasDone = completed.has(step.id);
    persist((prev) => toggleStep(prev, slug, step.id));
    if (!wasDone) {
      setJustCompleted(true);
      window.setTimeout(() => setJustCompleted(false), 4000);
    }
  }

  function handleGoToNextStep() {
    if (nextStepId) setActiveStepId(nextStepId);
  }

  async function handleMentorSend(userMessage: string, completedChecklist: string[]) {
    if (!slug) return;
    persist((prev) =>
      appendMentorMessage(prev, slug, {
        role: 'user',
        content: userMessage || '(Requested checklist review)',
      }),
    );

    const res = await fetch('/api/mentor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        projectSlug: slug,
        projectTitle: project!.title,
        step,
        userMessage,
        completedChecklist,
        note: state.notes[slug],
      }),
    });

    const data = await res.json();
    const replyText = [
      data.reply,
      '',
      '**Next action:** ' + data.feedback.nextAction,
      data.feedback.gaps.length ? '\n**Gaps:**\n- ' + data.feedback.gaps.join('\n- ') : '',
      data.feedback.strengths.length
        ? '\n**Strengths:**\n- ' + data.feedback.strengths.join('\n- ')
        : '',
    ]
      .filter(Boolean)
      .join('\n');

    persist((prev) =>
      appendMentorMessage(prev, slug, {
        role: 'mentor',
        content: replyText,
      }),
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
      <div>
        <Link href="/build" className="text-sm text-[var(--accent)] hover:underline">
          ← Build Lab
        </Link>
        <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
              Phase {project.phase} · {project.company}
            </p>
            <h1 className="text-2xl font-bold">{project.title}</h1>
            <p className="mt-2 max-w-2xl text-sm text-[var(--muted)]">{project.elevatorPitch}</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <div className="text-right">
              <div className="text-2xl font-bold text-[var(--accent)]">{pct}%</div>
              <div className="text-xs text-[var(--muted)]">project complete</div>
            </div>
            <a href="#milestones" className="btn-ghost text-sm">
              Jump to milestones
            </a>
            {demo?.localUrl && (
              <Link href={`/demos/${slug}`} className="btn-primary text-sm">
                Launch app demo
              </Link>
            )}
          </div>
        </div>
      </div>

      <div className="card !p-4 text-sm border-[var(--accent)]/20">
        <p className="text-xs font-semibold text-[var(--accent)]">How to use this page</p>
        <ol className="mt-2 list-inside list-decimal space-y-1 text-[var(--muted)]">
          <li>
            <Link href={`/demos/${slug}`} className="text-[var(--accent)] hover:underline">
              Try the demo
            </Link>{' '}
            first (if available) — use practice data, no file prep needed.
          </li>
          <li>Check off items you verified in the checklist below.</li>
          <li>
            Click <strong className="text-[var(--text)]">Mark step complete</strong> when done, then
            continue to the next step.
          </li>
        </ol>
      </div>

      <div className="card !p-4 text-sm">
        <strong>Resume bullet:</strong>{' '}
        <span className="text-[var(--muted)]">{project.resumeAnchor}</span>
        <div className="mt-2">
          <strong>Build folder:</strong>{' '}
          <code className="text-[var(--accent)]">{project.repoFolder}/</code>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <span className="rounded border border-[var(--border)] px-2 py-0.5 text-xs">
            {DOMAIN_LABELS[project.domain] ?? project.domain}
          </span>
          {project.stack.slice(0, 3).map((t) => (
            <span key={t} className="rounded border border-[var(--border)] px-2 py-0.5 text-xs">
              {t}
            </span>
          ))}
        </div>
      </div>

      {justCompleted && (
        <div
          className="rounded-lg border border-[var(--success)] bg-[color-mix(in_srgb,var(--success)_10%,transparent)] px-4 py-3 text-sm"
          role="status"
        >
          Saved! Step marked complete — progress is now {pct}%. Check the green checkmark in the
          milestone list on the left.
        </div>
      )}

      <AudioTutorPanel
        projectTitle={project.title}
        step={step}
        stepNumber={stepNum}
        totalSteps={stepTotal}
        lastMentorReply={lastMentorReply}
      />

      <div className="grid gap-6 lg:grid-cols-12">
        <aside className="lg:col-span-4">
          <MilestoneTracker
            milestones={project.milestones}
            activeStepId={activeStepId}
            completed={completed}
            onSelectStep={setActiveStepId}
          />
        </aside>

        <div className="space-y-6 lg:col-span-4">
          <StepGuide
            step={step}
            completedChecklist={checklist}
            onToggleChecklist={handleToggleChecklist}
            onToggleStepComplete={handleToggleStepComplete}
            onGoToNextStep={handleGoToNextStep}
            hasNextStep={!!nextStepId}
            stepMarkedComplete={stepDone}
          />

          <div className="card">
            <label htmlFor="project-notes" className="text-sm font-semibold">
              Build notes
            </label>
            <textarea
              id="project-notes"
              rows={4}
              className="mt-2"
              placeholder="Branch name, blockers, commands that worked…"
              value={state.notes[slug] ?? ''}
              onChange={(e) => persist((prev) => setNote(prev, slug, e.target.value))}
            />
          </div>
        </div>

        <div className="lg:col-span-4">
          <MentorPanel
            projectTitle={project.title}
            step={step}
            messages={messages}
            onSend={handleMentorSend}
            completedChecklist={checklist}
          />
        </div>
      </div>
    </div>
  );
}
