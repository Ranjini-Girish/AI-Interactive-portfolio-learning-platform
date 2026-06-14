import { getLabRun } from '@/lib/lab/store';
import { notFound } from 'next/navigation';

export default async function LabProofPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const run = await getLabRun(id);

  if (!run) {
    notFound();
  }

  const bullets = Array.isArray(run.bullets) ? (run.bullets as string[]) : [];
  const metrics = run.metrics as Record<string, unknown>;

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-12 sm:px-6">
      <header>
        <p className="text-sm font-medium uppercase tracking-wide text-[var(--accent)]">
          Lab proof · {run.lab_slug}
        </p>
        <h1 className="mt-2 text-2xl font-bold">{run.title}</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Completed {new Date(run.created_at).toLocaleString()}
          {run.model ? ` · ${run.provider} / ${run.model}` : run.provider ? ` · ${run.provider}` : ''}
        </p>
      </header>

      <section className="card">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
          Stakeholder summary
        </h2>
        <p className="mt-3 leading-relaxed">{run.summary}</p>
      </section>

      {bullets.length > 0 && (
        <section className="card">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
            Segment highlights
          </h2>
          <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-[var(--muted)]">
            {bullets.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </section>
      )}

      {Object.keys(metrics).length > 0 && (
        <section className="card">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
            Metrics
          </h2>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            {Object.entries(metrics).map(([k, v]) => (
              <div key={k}>
                <dt className="text-[var(--muted)]">{k}</dt>
                <dd className="font-medium">{String(v)}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <p className="text-center text-xs text-[var(--muted)]">
        Share this link on your resume or LinkedIn as proof you completed the lab.
      </p>
    </div>
  );
}
