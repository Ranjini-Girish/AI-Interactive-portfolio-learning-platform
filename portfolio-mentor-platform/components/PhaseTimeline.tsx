import { phases } from '@/data/curriculum';

export function PhaseTimeline({ activePhase }: { activePhase?: number }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {phases.map((p) => {
        const active = activePhase === p.id;
        return (
          <div
            key={p.id}
            className={`card ${active ? 'border-[var(--accent)] ring-1 ring-[var(--accent)]/40' : ''}`}
          >
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--accent)]">
              Phase {p.id} · {p.weeks}
            </div>
            <h3 className="mt-1 font-semibold">{p.label}</h3>
            <p className="mt-2 text-sm text-[var(--muted)]">{p.focus}</p>
          </div>
        );
      })}
    </div>
  );
}
