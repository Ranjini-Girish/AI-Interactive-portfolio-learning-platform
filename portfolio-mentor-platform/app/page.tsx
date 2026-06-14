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
            Prove resume projects before your next interview
          </p>
          <h1 className="mt-4 max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl">
            Turn ML projects into proof recruiters can click
          </h1>
          <p className="mt-4 max-w-2xl text-lg text-[var(--muted)]">
            {learner.name} · {learner.title}
          </p>
          <p className="mt-6 max-w-2xl leading-relaxed text-[var(--muted)]">
            Most candidates list AI projects hiring managers never see. This site gives you{' '}
            <strong className="text-[var(--text)]">working apps</strong> tied to real banking, retail,
            and insurance work — plus guided paths so you can demo and explain them on a call, starting
            in about five minutes.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/demos/customer-segmentation-lab" className="btn-primary">
              Prove my first project →
            </Link>
            <Link href="/start" className="btn-ghost">
              How it works
            </Link>
            <Link href="/interview" className="btn-ghost">
              Interview this week?
            </Link>
            <Link href="/portfolio" className="btn-ghost">
              Browse all apps
            </Link>
          </div>
          <div className="mt-12 grid max-w-lg grid-cols-3 gap-4">
            <Stat value={`${built}`} label="Apps to demo" />
            <Stat value={`${projects.length}`} label="Project stories" />
            <Stat value="5 min" label="First win" />
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
        <BeginnerPath />
      </section>

      <section className="border-y border-[var(--border)] bg-[var(--surface)]">
        <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
          <h2 className="text-2xl font-bold">Built for job seekers, not tourists</h2>
          <p className="mt-3 max-w-3xl text-[var(--muted)] leading-relaxed">
            Certificates show you watched videos. Recruiters want to know what you{' '}
            <strong className="text-[var(--text)]">actually built</strong>. Each project here is a live
            app with a learning path — so you can open it, run it, and talk through it under pressure.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <FeatureCard
              title="Clickable proof"
              body="Open real demos — group bank customers, predict churn, get recommendations. One click loads practice data."
              href="/demos/customer-segmentation-lab"
              cta="Prove first project"
            />
            <FeatureCard
              title="Interview-ready stories"
              body="Checklists, audio tutor, and AI mentor help you turn each demo into a 60-second answer."
              href="/build"
              cta="Open learning paths"
            />
            <FeatureCard
              title="Real industry context"
              body="Projects mirror work at banks, retailers, insurers, and tech teams — not toy Kaggle clones."
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
          <h2 className="text-xl font-bold">Your first proof point — about 5 minutes</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm text-[var(--muted)]">
            Customer Grouping Lab groups bank customers by spending. Practice data included, plain English
            on every screen — no coding required for Project 1.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <Link href="/demos/customer-segmentation-lab" className="btn-primary">
              Prove my first project →
            </Link>
            <Link href="/start" className="btn-ghost">
              Step-by-step guide
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
