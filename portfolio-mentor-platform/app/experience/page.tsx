import Link from 'next/link';
import { projects } from '@/data/curriculum';
import { experience, summary } from '@/data/resume';

export default function ExperiencePage() {
  return (
    <div className="mx-auto max-w-4xl space-y-10 px-4 py-8 sm:px-6">
      <header>
        <h1 className="text-3xl font-bold">Experience</h1>
        <ul className="mt-4 space-y-2 text-[var(--muted)]">
          {summary.map((s) => (
            <li key={s.slice(0, 40)} className="leading-relaxed">
              {s}
            </li>
          ))}
        </ul>
      </header>

      <div className="space-y-6">
        {experience.map((job) => {
          const related = projects.filter((p) => p.company === job.company);
          return (
            <article key={job.company} className="card">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div>
                  <h2 className="text-xl font-semibold">{job.role}</h2>
                  <p className="text-[var(--accent)]">
                    {job.company} · {job.location}
                  </p>
                </div>
                <p className="text-sm text-[var(--muted)]">{job.period}</p>
              </div>
              <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-[var(--muted)]">
                {job.highlights.map((h) => (
                  <li key={h.slice(0, 50)}>{h}</li>
                ))}
              </ul>
              {related.length > 0 && (
                <div className="mt-4 border-t border-[var(--border)] pt-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                    Portfolio apps from this role
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {related.map((p) => (
                      <Link
                        key={p.slug}
                        href={`/portfolio`}
                        className="rounded-lg border border-[var(--border)] px-2 py-1 text-xs hover:border-[var(--accent)]"
                      >
                        {p.title}
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
