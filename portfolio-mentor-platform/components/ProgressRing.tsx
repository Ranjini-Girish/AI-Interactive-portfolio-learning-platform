'use client';

import { useEffect, useState } from 'react';
import {
  loadProgress,
  overallProgress,
  type ProgressState,
} from '@/lib/progress';
import { projects, totalSteps } from '@/data/curriculum';

export function ProgressRing({ pct, size = 56 }: { pct: number; size?: number }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;

  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="var(--border)"
        strokeWidth="6"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="6"
        strokeDasharray={c}
        strokeDashoffset={offset}
        strokeLinecap="round"
      />
    </svg>
  );
}

export function usePortfolioProgress() {
  const [state, setState] = useState<ProgressState | null>(null);

  useEffect(() => {
    setState(loadProgress());
    const onStorage = () => setState(loadProgress());
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const summary = projects.map((p) => ({
    slug: p.slug,
    stepCount: totalSteps(p),
  }));

  const pct = state ? overallProgress(state, summary) : 0;

  return { state, pct, refresh: () => setState(loadProgress()) };
}

export function OverallProgressBanner() {
  const { pct } = usePortfolioProgress();

  return (
    <div className="card flex flex-wrap items-center gap-4 border-[var(--accent)]/30 bg-[color-mix(in_srgb,var(--accent)_8%,var(--surface))]">
      <div className="relative flex items-center justify-center">
        <ProgressRing pct={pct} size={64} />
        <span className="absolute text-sm font-bold">{pct}%</span>
      </div>
      <div className="min-w-0 flex-1">
        <h2 className="text-lg font-semibold">Portfolio build progress</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          {projects.length} resume-backed projects · 4 phases · check off steps as you ship
          each app under <code className="text-[var(--accent)]">apps/</code>.
        </p>
      </div>
    </div>
  );
}
