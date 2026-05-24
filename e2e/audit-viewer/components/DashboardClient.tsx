'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { StatusBadge } from './LogPanel';

type RunSummary = {
  runId: string;
  taskSlug: string;
  revisionTaskId?: string;
  startedAt: string;
  updatedAt: string;
  status: 'running' | 'success' | 'failed';
  eventCount: number;
  lastStep?: string;
  submitted?: boolean;
  revisionReasons?: string[];
  errorMessage?: string;
};

type TaskSummary = {
  slug: string;
  mtime: string;
  revisionTaskId?: string;
  status: 'running' | 'success' | 'failed';
  lastStep?: string;
  submitted?: boolean;
};

type DashboardData = {
  auditDir: string;
  exists: boolean;
  runs: RunSummary[];
  tasks: TaskSummary[];
};

export function DashboardClient() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [liveCount, setLiveCount] = useState(0);

  const refresh = useCallback(async () => {
    const res = await fetch('/api/runs');
    setData(await res.json());
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    const es = new EventSource('/api/stream?offset=0');
    es.onmessage = (ev) => {
      const msg = JSON.parse(ev.data) as { type: string; events?: unknown[] };
      if (msg.type === 'events' && msg.events?.length) {
        setLiveCount((c) => c + msg.events!.length);
        refresh();
      }
    };
    return () => es.close();
  }, [refresh]);

  if (!data) {
    return <p className="text-[var(--muted)]">Loading audit data…</p>;
  }

  if (!data.exists) {
    return (
      <div className="card">
        <p className="text-[var(--danger)]">Audit directory not found:</p>
        <code className="log-line mt-2 block text-xs">{data.auditDir}</code>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-wrap items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold">Revision flows</h1>
          <p className="text-sm text-[var(--muted)]">
            {data.runs.length} runs · {data.tasks.length} task logs ·{' '}
            <span className="text-[var(--accent)]">{liveCount} live events</span>
          </p>
        </div>
        <Link href="/live" className="badge badge-running ml-auto">
          Open live tail →
        </Link>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Latest per task</h2>
        <div className="grid gap-2">
          {data.tasks.slice(0, 20).map((t) => (
            <Link
              key={t.slug}
              href={`/tasks/${encodeURIComponent(t.slug)}`}
              className="card flex flex-wrap items-center gap-3 transition hover:border-[var(--accent)]"
            >
              <span className="font-medium">{t.slug}</span>
              <StatusBadge status={t.status} />
              {t.submitted ? (
                <span className="badge badge-success">submitted</span>
              ) : null}
              <span className="text-xs text-[var(--muted)]">{t.lastStep ?? '—'}</span>
              <span className="ml-auto text-xs text-[var(--muted)]">
                {new Date(t.mtime).toLocaleString()}
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">All runs (jsonl)</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--muted)]">
                <th className="py-2 pr-4">Task</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Last step</th>
                <th className="py-2 pr-4">Events</th>
                <th className="py-2 pr-4">Updated</th>
                <th className="py-2">UID</th>
              </tr>
            </thead>
            <tbody>
              {data.runs.map((r) => (
                <tr key={r.runId} className="border-b border-[var(--border)]/50">
                  <td className="py-2 pr-4">
                    <Link
                      href={`/runs/${encodeURIComponent(r.runId)}`}
                      className="text-[var(--accent)] hover:underline"
                    >
                      {r.taskSlug}
                    </Link>
                  </td>
                  <td className="py-2 pr-4">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="py-2 pr-4 log-line text-xs">{r.lastStep ?? '—'}</td>
                  <td className="py-2 pr-4">{r.eventCount}</td>
                  <td className="py-2 pr-4 text-xs text-[var(--muted)]">
                    {new Date(r.updatedAt).toLocaleString()}
                  </td>
                  <td className="py-2 log-line text-xs text-[var(--muted)]">
                    {r.revisionTaskId?.slice(0, 8) ?? '—'}…
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
