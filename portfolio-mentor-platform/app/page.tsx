import Link from 'next/link';
import { learner, projects } from '@/data/curriculum';
import { scaffoldedCount } from '@/data/demos';
import { contact, skillGroups, summary } from '@/data/resume';
import { BeginnerPath } from '@/components/BeginnerPath';

export default function HomePage() {
  const built = scaffoldedCount();

  return (
    <div>
      <section className="hero-gradient border-b border-[var(--border)]">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-24">
          <p className="text-sm font-medium uppercase tracking-widest text-[var(--accent)]">
            AI Portfolio & Hands-On Learning — no coding required to start
          </p>
          <h1 className="mt-4 max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl">
            {learner.name}
          </h1>
          <p className="mt-4 max-w-2xl text-lg text-[var(--muted)]">{learner.title}</p>
          <p className="mt-6 max-w-2xl leading-relaxed text-[var(--muted)]">
            Real job projects turned into <strong className="text-[var(--text)]">apps you can try</strong>
            — with step-by-step guidance and an AI helper. Built for learners, career changers, and
            anyone curious about AI and data work.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/start" className="btn-primary">
              New here? Start here
            </Link>
            <Link href="/demos/customer-segmentation-lab" className="btn-ghost">
              Try first app (5 min)
            </Link>
            <Link href="/portfolio" className="btn-ghost">
              Browse all apps
            </Link>
          </div>
          <div className="mt-12 grid max-w-lg grid-cols-3 gap-4">
            <Stat value={`${built}`} label="Apps to try" />
            <Stat value={`${projects.length}`} label="Learning topics" />
            <Stat value="4" label="Industry areas" />
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
        <BeginnerPath />
      </section>

      <section className="border-y border-[var(--border)] bg-[var(--surface)]">
        <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
          <h2 className="text-2xl font-bold">What makes this different</h2>
          <p className="mt-3 max-w-3xl text-[var(--muted)] leading-relaxed">
            Most resumes list projects you cannot see or touch. Here, each project is a{' '}
            <strong className="text-[var(--text)]">working app</strong> with a guided learning path —
            banking, shopping, insurance, and AI assistants.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <FeatureCard
              title="Try live apps"
              body="Open real demos — group bank customers, predict churn, get product recommendations. Click and learn."
              href="/portfolio"
              cta="See all apps"
            />
            <FeatureCard
              title="Guided learning path"
              body="Small steps, checklists, audio tutor, and AI mentor chat. Mark progress as you go."
              href="/build"
              cta="Open learning paths"
            />
            <FeatureCard
              title="Real work history"
              body="See how portfolio projects connect to jobs at banks, retailers, insurers, and tech companies."
              href="/experience"
              cta="View experience"
            />
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
        <h2 className="text-2xl font-bold">Skills covered</h2>
        <p className="mt-2 text-sm text-[var(--muted)]">
          You will encounter these over time — no need to know them on day one.
        </p>
        <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(skillGroups).map(([group, skills]) => (
            <div key={group}>
              <h3 className="text-sm font-semibold text-[var(--accent)]">{group}</h3>
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {skills.map((s) => (
                  <li
                    key={s}
                    className="rounded-md border border-[var(--border)] px-2 py-0.5 text-xs text-[var(--muted)]"
                  >
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
        <div className="card border-[var(--accent)]/30 bg-[color-mix(in_srgb,var(--accent)_6%,var(--surface))] text-center">
          <h2 className="text-xl font-bold">Ready in one click</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm text-[var(--muted)]">
            Project 1 groups bank customers by spending — practice data included, plain English on
            every screen.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <Link href="/demos/customer-segmentation-lab" className="btn-primary">
              Try Customer Grouping Lab
            </Link>
            <Link href="/build/projects/customer-segmentation-lab" className="btn-ghost">
              Open learning path
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="card !p-4 text-center">
      <div className="text-2xl font-bold text-[var(--accent)]">{value}</div>
      <div className="mt-1 text-xs text-[var(--muted)]">{label}</div>
    </div>
  );
}

function FeatureCard({
  title,
  body,
  href,
  cta,
}: {
  title: string;
  body: string;
  href: string;
  cta: string;
}) {
  return (
    <Link href={href} className="card card-hover block">
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-2 text-sm text-[var(--muted)]">{body}</p>
      <span className="mt-4 inline-block text-sm text-[var(--accent)]">{cta} →</span>
    </Link>
  );
}
