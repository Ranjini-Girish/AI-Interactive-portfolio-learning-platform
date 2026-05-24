'use client';

type LogEntry = {
  ts: string;
  phase: string;
  step: string;
  detail?: string;
  data?: Record<string, unknown>;
};

export function LogPanel({
  entries,
  title = 'Event log',
  autoScroll = true,
}: {
  entries: LogEntry[];
  title?: string;
  autoScroll?: boolean;
}) {
  return (
    <div className="card flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="text-xs text-[var(--muted)]">{entries.length} events</span>
      </div>
      <div
        className="max-h-[28rem] overflow-y-auto rounded-md border border-[var(--border)] bg-[var(--bg)] p-3"
        ref={(el) => {
          if (autoScroll && el) el.scrollTop = el.scrollHeight;
        }}
      >
        {entries.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">No log entries yet.</p>
        ) : (
          entries.map((e, i) => <LogLine key={`${e.ts}-${e.step}-${i}`} entry={e} />)
        )}
      </div>
    </div>
  );
}

function LogLine({ entry }: { entry: LogEntry }) {
  const phaseColor =
    entry.phase === 'error'
      ? 'text-[var(--danger)]'
      : entry.phase === 'done'
        ? 'text-[var(--success)]'
        : entry.phase === 'start'
          ? 'text-[var(--warning)]'
          : 'text-[var(--accent)]';

  return (
    <div className="log-line border-b border-[var(--border)]/40 py-2 last:border-0">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-[var(--muted)]">{formatTs(entry.ts)}</span>
        <span className={`font-semibold uppercase ${phaseColor}`}>{entry.phase}</span>
        <span className="text-[var(--text)]">{entry.step}</span>
      </div>
      {entry.detail ? <p className="mt-0.5 text-[var(--muted)]">{entry.detail}</p> : null}
      {entry.data ? (
        <pre className="mt-1 max-h-32 overflow-auto rounded bg-[var(--surface-2)] p-2 text-[0.65rem] text-[var(--muted)]">
          {JSON.stringify(entry.data, null, 2)}
        </pre>
      ) : null}
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

export function StatusBadge({ status }: { status: 'running' | 'success' | 'failed' }) {
  const cls =
    status === 'success'
      ? 'badge-success'
      : status === 'failed'
        ? 'badge-danger'
        : 'badge-running';
  return <span className={`badge ${cls}`}>{status}</span>;
}
