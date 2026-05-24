'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { IconActivity, IconChevronRight, IconLayoutGrid, IconRadio, IconSearch } from './icons';
import { StatusBadge } from './LogPanel';
import { StatCard } from './ui/StatCard';
import { DashboardSkeleton } from './ui/Skeleton';

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
  const [query, setQuery] = useState('');

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

  const stats = useMemo(() => {
    if (!data) return null;
    const running = data.runs.filter((r) => r.status === 'running').length;
    const failed = data.runs.filter((r) => r.status === 'failed').length;
    const submitted = data.tasks.filter((t) => t.submitted).length;
    return { running, failed, submitted };
  }, [data]);

  const filteredTasks = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    if (!q) return data.tasks;
    return data.tasks.filter((t) => t.slug.toLowerCase().includes(q));
  }, [data, query]);

  if (!data) {
    return <DashboardSkeleton />;
  }

  if (!data.exists) {
    return (
      <div className="card">
        <p className="text-[var(--danger)] font-medium">Audit directory not found</p>
        <code className="log-line mt-2 block text-xs text-[var(--muted)]">{data.auditDir}</code>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title">Revision flows</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Snorkel E2E revision automation · polling every 5s
          </p>
        </div>
        <Link href="/live" className="badge badge-running badge-link">
          <IconRadio className="h-3.5 w-3.5" />
          Live tail
          <IconChevronRight className="h-3.5 w-3.5" />
        </Link>
      </section>

      {stats ? (
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Summary">
          <StatCard
            label="Total runs"
            value={data.runs.length}
            hint="From revision-runs.jsonl"
            icon={<IconLayoutGrid className="h-4 w-4" />}
          />
          <StatCard
            label="Task logs"
            value={data.tasks.length}
            hint="Latest per slug"
            icon={<IconActivity className="h-4 w-4" />}
          />
          <StatCard
            label="Live events"
            value={liveCount}
            hint="SSE stream this session"
            accent="live"
            icon={<span className="live-dot inline-block h-2 w-2 rounded-full bg-[var(--accent)]" />}
          />
          <StatCard
            label="Running / failed"
            value={`${stats.running} / ${stats.failed}`}
            hint={`${stats.submitted} submitted`}
            accent={stats.failed > 0 ? 'danger' : stats.running > 0 ? 'live' : 'success'}
          />
        </section>
      ) : null}

      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="section-title mb-0">Latest per task</h2>
          <div className="search-wrap">
            <IconSearch className="h-4 w-4" />
            <input
              type="search"
              placeholder="Filter tasks…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="search-input"
              aria-label="Filter tasks"
            />
          </div>
        </div>
        <div className="grid gap-2">
          {filteredTasks.length === 0 ? (
            <div className="card text-sm text-[var(--muted)]">No tasks match your filter.</div>
          ) : (
            filteredTasks.slice(0, 24).map((t) => (
              <Link
                key={t.slug}
                href={`/tasks/${encodeURIComponent(t.slug)}`}
                className="card card-interactive flex flex-wrap items-center gap-3"
              >
                <span className="font-medium">{t.slug}</span>
                <StatusBadge status={t.status} />
                {t.submitted ? <span className="badge badge-success">submitted</span> : null}
                <span className="log-line text-xs text-[var(--muted)]">{t.lastStep ?? '—'}</span>
                <span className="ml-auto text-xs text-[var(--muted)]">
                  {new Date(t.mtime).toLocaleString()}
                </span>
                <IconChevronRight className="ml-1 h-4 w-4 text-[var(--muted)]" />
              </Link>
            ))
          )}
        </div>
      </section>

      <section>
        <h2 className="section-title">All runs</h2>
        <div className="card overflow-x-auto p-0">
          <table className="data-table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Status</th>
                <th>Last step</th>
                <th>Events</th>
                <th>Updated</th>
                <th>UID</th>
              </tr>
            </thead>
            <tbody>
              {data.runs.map((r) => (
                <tr key={r.runId}>
                  <td>
                    <Link href={`/runs/${encodeURIComponent(r.runId)}`} className="text-link">
                      {r.taskSlug}
                    </Link>
                  </td>
                  <td>
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="log-line text-xs">{r.lastStep ?? '—'}</td>
                  <td>{r.eventCount}</td>
                  <td className="text-xs text-[var(--muted)]">
                    {new Date(r.updatedAt).toLocaleString()}
                  </td>
                  <td className="log-line text-xs text-[var(--muted)]">
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
