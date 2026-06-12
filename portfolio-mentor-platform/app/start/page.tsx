import Link from 'next/link';
import { BeginnerPath } from '@/components/BeginnerPath';
import { GLOSSARY } from '@/lib/beginner-guide';

const DEMO_PATH = '/demos/customer-segmentation-lab';
const LEARN_PATH = '/build/projects/customer-segmentation-lab#step-guide';

export default function StartHerePage() {
  return (
    <div className="mx-auto max-w-4xl space-y-10 px-4 py-10 sm:px-6">
      <header className="text-center">
        <p className="text-sm font-medium uppercase tracking-wide text-[var(--accent)]">
          Applying to AI/ML roles? Prove one project before your next screen.
        </p>
        <h1 className="mt-3 text-3xl font-bold sm:text-4xl">
          Your resume says you built ML projects. Can you show them in 5 minutes?
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-[var(--muted)] leading-relaxed">
          Recruiters and hiring managers want <strong className="text-[var(--text)]">clickable proof</strong>,
          not another certificate. Try a real customer-grouping app with practice bank data — no spreadsheet,
          no coding for Project 1 — and leave with a story you can use on a call.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link href={DEMO_PATH} className="btn-primary">
            Prove my first project →
          </Link>
          <Link href="/interview" className="btn-ghost">
            Interview this week?
          </Link>
        </div>
      </header>

      <div className="card border-[var(--warning)]/35 bg-[color-mix(in_srgb,var(--warning)_6%,var(--surface))] text-sm">
        <strong className="text-[var(--warning)]">Who this is for</strong>
        <p className="mt-2 text-[var(--muted)]">
          Career changers, bootcamp grads, and junior AI/ML candidates who list projects on a resume but
          struggle to demo them live. If you have a recruiter screen or application deadline soon, start
          here — not with another video course.
        </p>
      </div>

      <BeginnerPath />

      <section className="card space-y-4">
        <h2 className="text-lg font-bold">Your first 5 minutes (in the browser)</h2>
        <p className="text-sm text-[var(--muted)]">
          No install required on this site. Everything below works from your phone or laptop.
        </p>
        <ol className="space-y-4 text-sm">
          <li className="flex gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-xs font-bold text-white">
              1
            </span>
            <div>
              <strong>Open the Customer Grouping Lab</strong>
              <p className="mt-1 text-[var(--muted)]">
                Click{' '}
                <Link href={DEMO_PATH} className="text-[var(--accent)] hover:underline">
                  Prove my first project
                </Link>
                , then <strong>Open app</strong> in a new tab. If the demo is not hosted yet, use the{' '}
                <Link href={LEARN_PATH} className="text-[var(--accent)] hover:underline">
                  learning path
                </Link>{' '}
                — same project, step-by-step.
              </p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-xs font-bold text-white">
              2
            </span>
            <div>
              <strong>Load practice data</strong>
              <p className="mt-1 text-[var(--muted)]">
                Click <strong>Start with practice data</strong> — no CSV upload, no Python setup.
              </p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-xs font-bold text-white">
              3
            </span>
            <div>
              <strong>Create groups and read the chart</strong>
              <p className="mt-1 text-[var(--muted)]">
                In Step 2, click <strong>Create customer groups</strong>. Scroll to the chart and customer
                lists — that is your proof-of-work screenshot moment.
              </p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-xs font-bold text-white">
              4
            </span>
            <div>
              <strong>Turn it into an interview story</strong>
              <p className="mt-1 text-[var(--muted)]">
                Open{' '}
                <Link href={LEARN_PATH} className="text-[var(--accent)] hover:underline">
                  the learning path
                </Link>
                , mark steps complete, and practice a 60-second &ldquo;what I built&rdquo; answer. Running
                locally? Double-click <code className="text-[var(--accent)]">START-PORTFOLIO.bat</code> for
                the full interactive demo.
              </p>
            </div>
          </li>
        </ol>
      </section>

      <section className="card">
        <h2 className="text-lg font-bold">Why this beats another course</h2>
        <ul className="mt-4 space-y-3 text-sm text-[var(--muted)]">
          <li>
            <strong className="text-[var(--text)]">Certificates</strong> — no proof you executed the work.
            Here, recruiters can open the app.
          </li>
          <li>
            <strong className="text-[var(--text)]">GitHub repos</strong> — often broken or intimidating.
            Here, one click loads practice data.
          </li>
          <li>
            <strong className="text-[var(--text)]">Slide decks</strong> — not credible in a screen.
            Here, you click buttons and see results.
          </li>
        </ul>
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

      <div className="flex flex-wrap justify-center gap-3">
        <Link href={DEMO_PATH} className="btn-primary text-sm">
          Prove my first project →
        </Link>
        <Link href="/portfolio" className="btn-ghost text-sm">
          Browse all topics →
        </Link>
      </div>
    </div>
  );
}
