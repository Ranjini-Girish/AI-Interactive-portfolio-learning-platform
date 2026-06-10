'use client';

import Link from 'next/link';
import { learner, phases, projects } from '@/data/curriculum';
import { OverallProgressBanner } from '@/components/ProgressRing';
import { PhaseTimeline } from '@/components/PhaseTimeline';
import { ProjectCard } from '@/components/ProjectCard';
import { RECOMMENDED_FIRST } from '@/lib/beginner-guide';

export default function BuildLabPage() {
  const byPhase = phases.map((ph) => ({
    ...ph,
    items: projects.filter((p) => p.phase === ph.id),
  }));

  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 py-8 sm:px-6">
      <section className="space-y-4">
        <div>
          <p className="text-sm text-[var(--success)]">Step-by-step — go at your own pace</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">Learning paths</h1>
          <p className="mt-2 max-w-2xl text-[var(--muted)]">
            Each topic has small steps, a checklist, and an AI helper. Try the demo first, then come
            back here to mark what you completed. No rush — {learner.name}&apos;s full roadmap has{' '}
            {projects.length} projects across banking, retail, insurance, and AI.
          </p>
          <Link href="/start" className="mt-3 inline-block text-sm text-[var(--accent)] hover:underline">
            New here? Read the 5-minute guide →
          </Link>
        </div>
        <OverallProgressBanner />
      </section>

      <div className="card border-[var(--success)]/30 bg-[color-mix(in_srgb,var(--success)_6%,var(--surface))]">
        <p className="text-xs font-semibold uppercase text-[var(--success)]">Best for beginners</p>
        <h2 className="mt-1 text-lg font-bold">{RECOMMENDED_FIRST.title}</h2>
        <p className="mt-2 text-sm text-[var(--muted)]">{RECOMMENDED_FIRST.why}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link href={RECOMMENDED_FIRST.demoPath} className="btn-primary text-sm">
            Try demo first
          </Link>
          <Link href={RECOMMENDED_FIRST.learnPath} className="btn-ghost text-sm">
            Open learning path
          </Link>
        </div>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">14-week overview</h2>
        <p className="text-sm text-[var(--muted)]">A suggested order — skip around if you like.</p>
        <PhaseTimeline />
      </section>

      {byPhase.map((block) => (
        <section key={block.id} className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold">
              Phase {block.id}: {block.label}
            </h2>
            <p className="text-sm text-[var(--muted)]">Weeks {block.weeks}</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {block.items.map((p) => (
              <ProjectCard key={p.slug} project={p} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
