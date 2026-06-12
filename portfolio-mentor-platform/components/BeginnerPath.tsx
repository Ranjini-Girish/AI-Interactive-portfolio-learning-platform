import Link from 'next/link';
import { HOW_IT_WORKS, RECOMMENDED_FIRST } from '@/lib/beginner-guide';

export function BeginnerPath({ showCta = true }: { showCta?: boolean }) {
  return (
    <section className="space-y-6">
      <div>
        <p className="text-sm font-medium text-[var(--success)]">Proof before your next screen</p>
        <h2 className="mt-1 text-2xl font-bold">How it works in 3 steps</h2>
        <p className="mt-2 max-w-2xl text-sm text-[var(--muted)]">
          Turn a resume bullet into something you can demo — the same ideas used in real AI and data
          jobs, without starting from a blank notebook.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {HOW_IT_WORKS.map((item) => (
          <div key={item.step} className="card !p-4">
            <div className="text-2xl" aria-hidden>
              {item.icon}
            </div>
            <p className="mt-2 text-xs font-bold text-[var(--accent)]">Step {item.step}</p>
            <h3 className="mt-1 font-semibold">{item.title}</h3>
            <p className="mt-2 text-sm text-[var(--muted)]">{item.body}</p>
          </div>
        ))}
      </div>

      {showCta && (
        <div className="card border-[var(--success)]/40 bg-[color-mix(in_srgb,var(--success)_8%,var(--surface))] !p-5">
          <p className="text-sm font-semibold text-[var(--success)]">Start here — one 5-minute win</p>
          <h3 className="mt-1 text-lg font-bold">{RECOMMENDED_FIRST.title}</h3>
          <p className="mt-2 text-sm text-[var(--muted)]">{RECOMMENDED_FIRST.why}</p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link href={RECOMMENDED_FIRST.demoPath} className="btn-primary text-sm">
              Prove my first project →
            </Link>
            <Link href={RECOMMENDED_FIRST.learnPath} className="btn-ghost text-sm">
              Open learning path
            </Link>
          </div>
        </div>
      )}
    </section>
  );
}
