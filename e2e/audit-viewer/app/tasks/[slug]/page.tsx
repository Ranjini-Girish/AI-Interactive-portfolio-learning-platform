'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { IconArrowLeft } from '@/components/icons';
import { WorkflowTimeline } from '@/components/WorkflowTimeline';
import { LogPanel, StatusBadge } from '@/components/LogPanel';
import { Skeleton } from '@/components/ui/Skeleton';
import type { PhaseState } from '@/lib/workflow';

type TaskDetail = {
  slug: string;
  revisionTaskId?: string;
  mtime: string;
  workflow: PhaseState[];
  humanLog: Array<{
    ts: string;
    phase: string;
    step: string;
    detail?: string;
    data?: Record<string, unknown>;
  }>;
  context?: Record<string, unknown> | null;
  error?: string;
};

export default function TaskDetailPage() {
  const params = useParams();
  const slug = decodeURIComponent(String(params.slug ?? ''));
  const [data, setData] = useState<TaskDetail | null>(null);

  useEffect(() => {
    if (!slug) return;
    const load = () =>
      fetch(`/api/tasks/${encodeURIComponent(slug)}`)
        .then((r) => r.json())
        .then(setData);
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [slug]);

  if (!data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64 rounded-lg" />
        <Skeleton className="h-40 rounded-xl" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    );
  }
  if (data.error) return <p className="text-[var(--danger)]">{data.error}</p>;

  const status = data.humanLog.some((e) => e.phase === 'error')
    ? 'failed'
    : data.humanLog.some((e) => e.step === 'run_complete')
      ? 'success'
      : 'running';

  const logEntries = data.humanLog.map((e) => ({
    ts: e.ts,
    phase: e.phase,
    step: e.step,
    detail: e.detail,
    data: e.data,
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/" className="back-link">
          <IconArrowLeft className="h-4 w-4" />
          Dashboard
        </Link>
        <h1 className="page-title">{data.slug}</h1>
        <StatusBadge status={status} />
        <span className="text-xs text-[var(--muted)]">{new Date(data.mtime).toLocaleString()}</span>
        {data.revisionTaskId ? (
          <span className="log-line text-xs text-[var(--muted)]">UID {data.revisionTaskId}</span>
        ) : null}
      </div>

      <section>
        <h2 className="section-title">Workflow</h2>
        <WorkflowTimeline phases={data.workflow} />
      </section>

      <LogPanel entries={logEntries} title={`revision-${data.slug}-latest.log`} />

      {data.context ? (
        <div className="card">
          <h3 className="mb-2 text-sm font-semibold">Captured revision reasons</h3>
          <pre className="log-line max-h-48 overflow-auto text-xs text-[var(--muted)]">
            {JSON.stringify(data.context.revisionReasons, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
