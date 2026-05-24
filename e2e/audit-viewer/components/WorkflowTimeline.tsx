'use client';

import type { PhaseState } from '@/lib/workflow';

const STATUS_COLORS: Record<PhaseState['status'], string> = {
  pending: 'border-[var(--pending)] bg-[var(--surface-2)] text-[var(--muted)]',
  active:
    'border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_12%,transparent)] text-[var(--accent)]',
  done: 'border-[var(--success)] bg-[color-mix(in_srgb,var(--success)_10%,transparent)] text-[var(--success)]',
  error:
    'border-[var(--danger)] bg-[color-mix(in_srgb,var(--danger)_12%,transparent)] text-[var(--danger)]',
  skipped: 'border-[var(--border)] bg-transparent text-[var(--muted)]',
};

const DOT_COLORS: Record<PhaseState['status'], string> = {
  pending: 'bg-[var(--pending)]',
  active: 'bg-[var(--accent)] live-dot',
  done: 'bg-[var(--success)]',
  error: 'bg-[var(--danger)]',
  skipped: 'bg-[var(--border)]',
};

export function WorkflowTimeline({ phases }: { phases: PhaseState[] }) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {phases.map((phase, i) => (
        <div
          key={phase.id}
          className={`rounded-lg border p-3 transition-colors ${STATUS_COLORS[phase.status]}`}
        >
          <div className="flex items-start gap-2">
            <span
              className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${DOT_COLORS[phase.status]}`}
            />
            <div>
              <PhaseLabel index={i + 1} />
              <div className="text-sm font-semibold">{phase.label}</div>
            </div>
          </div>
          <p className="mt-1 text-xs opacity-80">{phase.description}</p>
          <ul className="mt-2 space-y-0.5">
            {phase.steps.map((step) => {
              const done = phase.completedSteps.includes(step);
              return (
                <li key={step} className="log-line flex items-center gap-1.5 text-[0.68rem]">
                  <span>{done ? '✓' : '○'}</span>
                  <span className={done ? 'opacity-100' : 'opacity-45'}>{step}</span>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

function PhaseLabel({ index }: { index: number }) {
  return (
    <div className="text-xs font-medium uppercase tracking-wide opacity-70">Phase {index}</div>
  );
}
