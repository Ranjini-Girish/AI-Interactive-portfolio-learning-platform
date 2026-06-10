import Link from 'next/link';
import { HOW_IT_WORKS, RECOMMENDED_FIRST } from '@/lib/beginner-guide';

export function BeginnerPath({ showCta = true }: { showCta?: boolean }) {
  return (
    <section className="space-y-6">
      <div>
        <p className="text-sm font-medium text-[var(--success)]">New here? No tech background needed</p>
        <h2 className="mt-1 text-2xl font-bold">How it works in 3 steps</h2>
        <p className="mt-2 max-w-2xl text-sm text-[var(--muted)]">
          Learn the same ideas used in real AI and data jobs — by trying working apps, not reading
          slides.
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
          <p className="text-sm font-semibold text-[var(--success)]">Recommended first activity</p>
          <h3 className="mt-1 text-lg font-bold">{RECOMMENDED_FIRST.title}</h3>
          <p className="mt-2 text-sm text-[var(--muted)]">{RECOMMENDED_FIRST.why}</p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link href={RECOMMENDED_FIRST.demoPath} className="btn-primary text-sm">
              Try it now (5 min)
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
