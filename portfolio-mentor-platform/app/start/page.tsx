import Link from 'next/link';
import { BeginnerPath } from '@/components/BeginnerPath';
import { GLOSSARY } from '@/lib/beginner-guide';

export default function StartHerePage() {
  return (
    <div className="mx-auto max-w-4xl space-y-10 px-4 py-10 sm:px-6">
      <header className="text-center">
        <p className="text-sm font-medium uppercase tracking-wide text-[var(--accent)]">
          Welcome — beginners & career changers
        </p>
        <h1 className="mt-3 text-3xl font-bold sm:text-4xl">Start here</h1>
        <p className="mx-auto mt-4 max-w-xl text-[var(--muted)] leading-relaxed">
          This site turns resume projects into <strong className="text-[var(--text)]">apps you can
          actually use</strong>. You do not need to know programming to try the first project.
        </p>
      </header>

      <BeginnerPath />

      <section className="card space-y-4">
        <h2 className="text-lg font-bold">Your first 5 minutes</h2>
        <ol className="space-y-4 text-sm">
          <li className="flex gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-xs font-bold text-white">
              1
            </span>
            <div>
              <strong>Start the apps on your computer</strong>
              <p className="mt-1 text-[var(--muted)]">
                Double-click <code className="text-[var(--accent)]">START-PORTFOLIO.bat</code> in
                the portfolio folder. Wait about 30 seconds.
              </p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-xs font-bold text-white">
              2
            </span>
            <div>
              <strong>Open the Customer Grouping Lab</strong>
              <p className="mt-1 text-[var(--muted)]">
                Click <Link href="/demos/customer-segmentation-lab" className="text-[var(--accent)] hover:underline">Try it now</Link>, then{' '}
                <strong>Open in new tab</strong>. Click{' '}
                <strong>Start with practice data</strong>.
              </p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-xs font-bold text-white">
              3
            </span>
            <div>
              <strong>Create groups and explore the chart</strong>
              <p className="mt-1 text-[var(--muted)]">
                In Step 2, click <strong>Create customer groups</strong>. Scroll down to see the
                colorful chart and customer lists.
              </p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-xs font-bold text-white">
              4
            </span>
            <div>
              <strong>Mark your progress</strong>
              <p className="mt-1 text-[var(--muted)]">
                Come back to{' '}
                <Link
                  href="/build/projects/customer-segmentation-lab#step-guide"
                  className="text-[var(--accent)] hover:underline"
                >
                  the learning path
                </Link>{' '}
                and click <strong>Mark step complete</strong> for each step you finished.
              </p>
            </div>
          </li>
        </ol>
      </section>

      <section className="card">
        <h2 className="text-lg font-bold">Words we use — in plain English</h2>
        <dl className="mt-4 space-y-3">
          {GLOSSARY.map((g) => (
            <div key={g.term} className="border-b border-[var(--border)] pb-3 last:border-0">
              <dt className="font-semibold text-[var(--accent)]">{g.term}</dt>
              <dd className="mt-1 text-sm text-[var(--muted)]">{g.plain}</dd>
            </div>
          ))}
        </dl>
      </section>

      <div className="text-center">
        <Link href="/portfolio" className="btn-ghost text-sm">
          Browse all topics →
        </Link>
      </div>
    </div>
  );
}
