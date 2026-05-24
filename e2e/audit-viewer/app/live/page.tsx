'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';

type StreamEvent = {
  ts: string;
  runId: string;
  phase: string;
  step?: string;
  detail?: string;
};

export default function LivePage() {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const es = new EventSource('/api/stream?offset=0');
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (ev) => {
      const msg = JSON.parse(ev.data) as { type: string; events?: StreamEvent[] };
      if (msg.type === 'events' && msg.events?.length) {
        setEvents((prev) => [...prev, ...msg.events!].slice(-500));
      }
    };
    return () => es.close();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  return (
    <div className="space-y-4">
      <LiveHeader connected={connected} eventCount={events.length} />
      <div className="card max-h-[70vh] overflow-y-auto font-mono text-xs">
        {events.length === 0 ? (
          <p className="text-[var(--muted)]">
            Waiting for revision-runs.jsonl events… Run a Playwright revision flow to see live
            steps.
          </p>
        ) : (
          events.map((e, i) => (
            <div key={`${e.runId}-${e.ts}-${i}`} className="border-b border-[var(--border)]/40 py-2">
              <span className="text-[var(--muted)]">{formatTs(e.ts)}</span>{' '}
              <span className="text-[var(--accent)]">{slugFromRun(e.runId)}</span>{' '}
              <span className="uppercase text-[var(--warning)]">{e.phase}</span> <span>{e.step}</span>
              {e.detail ? <span className="text-[var(--muted)]"> — {e.detail}</span> : null}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function LiveHeader({
  connected,
  eventCount,
}: {
  connected: boolean;
  eventCount: number;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Link href="/" className="text-sm text-[var(--muted)] hover:text-[var(--accent)]">
        ← Dashboard
      </Link>
      <h1 className="text-xl font-bold">Live tail</h1>
      <span className={`badge ${connected ? 'badge-running' : 'badge-pending'}`}>
        <span
          className={`mr-1 inline-block h-2 w-2 rounded-full ${connected ? 'live-dot bg-[var(--accent)]' : 'bg-[var(--pending)]'}`}
        />
        {connected ? 'connected' : 'disconnected'}
      </span>
      <span className="text-sm text-[var(--muted)]">{eventCount} events buffered</span>
    </div>
  );
}

function formatTs(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

function slugFromRun(runId: string): string {
  const m = runId.match(/^revision-(.+)-\d{4}-\d{2}-\d{2}T/);
  return m?.[1] ?? runId.slice(0, 24);
}
