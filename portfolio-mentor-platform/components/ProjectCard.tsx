'use client';

import Link from 'next/link';
import type { Project } from '@/data/curriculum';
import { projectProgress } from '@/lib/progress';
import { usePortfolioProgress } from '@/components/ProgressRing';
import { totalSteps, allStepIds } from '@/data/curriculum';
import { DOMAIN_LABELS } from '@/lib/beginner-guide';
import { demos } from '@/data/demos';

const domainClass: Record<Project['domain'], string> = {
  banking: 'domain-banking',
  retail: 'domain-retail',
  insurance: 'domain-insurance',
  genai: 'domain-genai',
};

export function ProjectCard({ project }: { project: Project }) {
  const { state } = usePortfolioProgress();
  const pct = state
    ? projectProgress(state, project.slug, allStepIds(project))
    : 0;
  const steps = totalSteps(project);
  const demo = demos[project.slug];
  const canTry = demo?.status === 'scaffolded' || demo?.status === 'live';

  return (
    <div className="card card-hover flex flex-col transition-all">
      <Link href={`/build/projects/${project.slug}`} className="block flex-1">
        <div className="flex items-start justify-between gap-2">
          <span className={`badge ${domainClass[project.domain]}`}>
            {DOMAIN_LABELS[project.domain] ?? project.domain}
          </span>
          {canTry ? (
            <span className="text-xs font-medium text-[var(--success)]">Ready to try</span>
          ) : (
            <span className="text-xs text-[var(--muted)]">~{project.estimatedHours}h</span>
          )}
        </div>
        <h3 className="mt-3 text-base font-semibold leading-snug">{project.title}</h3>
        <p className="mt-1 text-xs text-[var(--muted)]">{project.company}</p>
        <p className="mt-2 line-clamp-2 text-sm text-[var(--muted)]">{project.elevatorPitch}</p>
        <div className="mt-4">
          <div className="mb-1 flex justify-between text-xs">
            <span className="text-[var(--muted)]">
              {steps} steps · Phase {project.phase}
            </span>
            <span className="font-medium text-[var(--accent)]">{pct}% done</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-[var(--border)]">
            <div
              className="h-full rounded-full bg-[var(--accent)] transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      </Link>
      {canTry && (
        <Link
          href={`/demos/${project.slug}`}
          className="btn-primary mt-3 w-full text-center text-sm"
          onClick={(e) => e.stopPropagation()}
        >
          Try demo
        </Link>
      )}
    </div>
  );
}
