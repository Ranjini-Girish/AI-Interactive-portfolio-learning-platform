'use client';

import type { Step } from '@/data/curriculum';

type Props = {
  step: Step;
  completedChecklist: string[];
  onToggleChecklist: (item: string) => void;
  onToggleStepComplete: () => void;
  onGoToNextStep?: () => void;
  hasNextStep: boolean;
  stepMarkedComplete: boolean;
};

export function StepGuide({
  step,
  completedChecklist,
  onToggleChecklist,
  onToggleStepComplete,
  onGoToNextStep,
  hasNextStep,
  stepMarkedComplete,
}: Props) {
  const checkedCount = completedChecklist.length;
  const totalCount = step.verifyChecklist.length;

  return (
    <div className="card space-y-4" id="step-guide">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--accent)]">
          Current step
        </p>
        <h2 className="mt-1 text-xl font-bold">{step.title}</h2>
      </div>

      {stepMarkedComplete && (
        <div className="rounded-lg border border-[var(--success)] bg-[color-mix(in_srgb,var(--success)_12%,transparent)] px-4 py-3 text-sm">
          <strong className="text-[var(--success)]">Step marked complete.</strong>{' '}
          {hasNextStep
            ? 'Use the milestone list on the left or click Continue below.'
            : 'Great work — this milestone is done!'}
        </div>
      )}

      <div className="rounded-lg border border-[var(--border)] bg-[var(--bg)] p-4">
        <p className="text-sm leading-relaxed">{step.instruction}</p>
        {step.hint && (
          <p className="mt-3 border-t border-[var(--border)] pt-3 text-sm text-[var(--warning)]">
            Hint: {step.hint}
          </p>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold">Verification checklist</h3>
        <p className="mt-1 text-xs text-[var(--muted)]">
          Optional — check items you verified in the demo. You can mark the step complete anytime
          after practicing ({checkedCount}/{totalCount} checked).
        </p>
        <ul className="mt-3 space-y-2">
          {step.verifyChecklist.map((item, i) => {
            const checked = completedChecklist.includes(item);
            const inputId = `chk-${step.id}-${i}`;
            return (
              <li key={item} className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggleChecklist(item)}
                  className="mt-1"
                  id={inputId}
                />
                <label htmlFor={inputId} className="cursor-pointer">
                  {item}
                </label>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-primary" onClick={onToggleStepComplete}>
          {stepMarkedComplete ? 'Mark step incomplete' : 'Mark step complete'}
        </button>
        {stepMarkedComplete && hasNextStep && onGoToNextStep && (
          <button type="button" className="btn-ghost" onClick={onGoToNextStep}>
            Continue to next step →
          </button>
        )}
      </div>
    </div>
  );
}
