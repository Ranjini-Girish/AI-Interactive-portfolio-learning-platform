import Link from 'next/link';
import { projects } from '@/data/curriculum';
import { demos } from '@/data/demos';
import { DOMAIN_LABELS, STATUS_LABELS } from '@/lib/beginner-guide';

const domainClass: Record<string, string> = {
  banking: 'domain-banking',
  retail: 'domain-retail',
  insurance: 'domain-insurance',
  genai: 'domain-genai',
};

export default function PortfolioPage() {
  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 py-8 sm:px-6">
      <header>
        <p className="text-sm text-[var(--success)]">Click and explore — no setup knowledge needed</p>
        <h1 className="mt-1 text-3xl font-bold">Try the apps</h1>
        <p className="mt-2 max-w-2xl text-[var(--muted)]">
          Each card is a real project from hands-on work experience. Apps marked{' '}
          <strong className="text-[var(--success)]">Ready to try</strong> open in your browser.
          Start with <strong className="text-[var(--text)]">Customer Grouping Lab</strong> if you are
          new.
        </p>
        <Link href="/start" className="mt-3 inline-block text-sm text-[var(--accent)] hover:underline">
          First time? Start here guide →
        </Link>
      </header>

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {projects.map((p) => {
          const demo = demos[p.slug];
          const status = demo?.status ?? 'planned';
          const ready = status === 'scaffolded' || status === 'live';
          return (
            <article key={p.slug} className="card card-hover flex flex-col">
              <div className="flex items-center justify-between gap-2">
                <span className={`badge ${domainClass[p.domain]}`}>
                  {DOMAIN_LABELS[p.domain] ?? p.domain}
                </span>
                <span
                  className={`text-xs font-medium ${
                    ready ? 'text-[var(--success)]' : 'text-[var(--muted)]'
                  }`}
                >
                  {STATUS_LABELS[status] ?? status}
                </span>
              </div>
              <h2 className="mt-3 text-lg font-semibold">{p.title}</h2>
              <p className="text-xs text-[var(--muted)]">{p.company}</p>
              <p className="mt-2 flex-1 text-sm text-[var(--muted)]">{p.elevatorPitch}</p>
              <div className="mt-4 flex flex-wrap gap-2 border-t border-[var(--border)] pt-4">
                {ready && demo?.localUrl ? (
                  <Link href={`/demos/${p.slug}`} className="btn-primary text-sm">
                    Try it now
                  </Link>
                ) : (
                  <Link href={`/build/projects/${p.slug}`} className="btn-primary text-sm">
                    View learning path
                  </Link>
                )}
                <Link href={`/build/projects/${p.slug}`} className="btn-ghost text-sm">
                  Steps & progress
                </Link>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
