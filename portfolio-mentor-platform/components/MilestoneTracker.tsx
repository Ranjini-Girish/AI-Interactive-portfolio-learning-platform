'use client';

import type { Milestone } from '@/data/curriculum';

type Props = {
  milestones: Milestone[];
  activeStepId: string;
  completed: Set<string>;
  onSelectStep: (stepId: string) => void;
};

export function MilestoneTracker({
  milestones,
  activeStepId,
  completed,
  onSelectStep,
}: Props) {
  return (
    <div className="space-y-4" id="milestones">
      {milestones.map((m, mi) => (
        <div key={m.id} className="card !p-4">
          <div className="flex items-baseline gap-2">
            <span className="text-xs font-bold text-[var(--accent)]">M{mi + 1}</span>
            <h3 className="font-semibold">{m.title}</h3>
          </div>
          <p className="mt-1 text-xs text-[var(--muted)]">{m.outcome}</p>
          <ul className="mt-3 space-y-1">
            {m.steps.map((s) => {
              const done = completed.has(s.id);
              const active = s.id === activeStepId;
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => onSelectStep(s.id)}
                    className={`flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition-colors ${
                      active
                        ? 'bg-[color-mix(in_srgb,var(--accent)_15%,transparent)] text-[var(--accent)]'
                        : 'hover:bg-[var(--surface-2)]'
                    }`}
                  >
                    <span
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[0.65rem] ${
                        done
                          ? 'bg-[var(--success)] text-[#0a0e14]'
                          : 'border border-[var(--border)]'
                      }`}
                    >
                      {done ? '✓' : ''}
                    </span>
                    <span className={done ? 'text-[var(--muted)] line-through' : ''}>
                      {s.title}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
