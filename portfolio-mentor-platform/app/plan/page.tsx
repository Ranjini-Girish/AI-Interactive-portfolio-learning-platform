import Link from 'next/link';
import { learner, phases, projects } from '@/data/curriculum';

export default function PlanPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-8 px-4 py-8 sm:px-6">
      <div>
        <Link href="/build" className="text-sm text-[var(--accent)] hover:underline">
          ← Back to Build Lab
        </Link>
        <h1 className="mt-4 text-3xl font-bold">Mentoring plan</h1>
        <p className="mt-2 text-[var(--muted)]">
          Structured path from your resume bullets to deployable portfolio apps — with weekly
          goals and demo milestones.
        </p>
      </div>

      <section className="card">
        <h2 className="font-semibold">Learner profile</h2>
        <p className="mt-2 text-sm">
          <strong>{learner.name}</strong> · {learner.email}
        </p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-[var(--muted)]">
          {learner.summary.map((s) => (
            <li key={s.slice(0, 40)}>{s}</li>
          ))}
        </ul>
      </section>

      {phases.map((ph) => {
        const items = projects.filter((p) => p.phase === ph.id);
        return (
          <section key={ph.id} className="card">
            <h2 className="text-lg font-semibold">
              Phase {ph.id}: {ph.label}
            </h2>
            <p className="text-sm text-[var(--muted)]">
              Weeks {ph.weeks} · {ph.focus}
            </p>
            <table className="mt-4 w-full text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--muted)]">
                  <th className="pb-2 pr-4 font-medium">Project</th>
                  <th className="pb-2 pr-4 font-medium">Resume anchor</th>
                  <th className="pb-2 font-medium">Hours</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.slug} className="border-b border-[var(--border)]/50">
                    <td className="py-3 pr-4 align-top">
                      <Link
                        href={`/build/projects/${p.slug}`}
                        className="font-medium text-[var(--accent)] hover:underline"
                      >
                        {p.title}
                      </Link>
                      <div className="text-xs text-[var(--muted)]">{p.company}</div>
                    </td>
                    <td className="py-3 pr-4 align-top text-[var(--muted)]">
                      {p.resumeAnchor}
                    </td>
                    <td className="py-3 align-top">~{p.estimatedHours}h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        );
      })}

      <section className="card">
        <h2 className="font-semibold">Weekly rhythm (recommended)</h2>
        <ul className="mt-3 space-y-2 text-sm text-[var(--muted)]">
          <li>
            <strong className="text-[var(--text)]">Mon–Tue:</strong> Scaffold + first milestone
          </li>
          <li>
            <strong className="text-[var(--text)]">Wed–Thu:</strong> Core feature + tests
          </li>
          <li>
            <strong className="text-[var(--text)]">Fri:</strong> Mentor review + README case study
          </li>
          <li>
            <strong className="text-[var(--text)]">Weekend:</strong> Polish UI, record 2-min demo
            clip
          </li>
        </ul>
      </section>
    </div>
  );
}
